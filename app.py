import os
import sqlite3
import json
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
import datetime

app = Flask(__name__)

# Credenciais do Twilio (via variáveis de ambiente no Render)
account_sid = os.getenv("TWILIO_ACCOUNT_SID")
auth_token = os.getenv("TWILIO_AUTH_TOKEN")
TATUADOR_SENHA = os.getenv("TATUADOR_SENHA", "default_password")  # Defina no Render

if not account_sid or not auth_token:
    raise ValueError("Twilio credentials not found in environment variables. Check Render settings.")
client = Client(account_sid, auth_token)

# Estado para rastrear solicitações de orçamento
orcamento_requests = {}

# Número do tatuador
TATUADOR_NUMERO = "whatsapp:+5513978131504"

# Número base do bot para envios
BOT_NUMERO = "whatsapp:+5513991069988"

# Descrição dos tatuadores
TATUADORES = {
    "1": {"nome": "Lucas", "estilo": "Especialista em realismo e tatuagens detalhadas, ideal para retratos e desenhos complexos."},
    "2": {"nome": "Mariana", "estilo": "Focada em aquarela e traços delicados, perfeita para tatuagens coloridas e artísticas."}
}

# Inicializar banco de dados SQLite
def init_db():
    conn = sqlite3.connect('clientes.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS clientes
                 (numero TEXT PRIMARY KEY, ideia TEXT, tamanho_local TEXT, pagamento TEXT, data TEXT, consentimento TEXT)''')
    conn.commit()
    conn.close()

    conn = sqlite3.connect('agenda.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS agenda
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, dia TEXT, horario TEXT, numero TEXT, ideia TEXT, status TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS conversations
                 (numero TEXT PRIMARY KEY, step INTEGER, data TEXT)''')  # data como JSON
    conn.commit()
    conn.close()

# Salvar dados do cliente (SQLite)
def save_to_db(from_number, ideia, tamanho_local, pagamento, consent):
    conn = sqlite3.connect('clientes.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS clientes
                 (numero TEXT PRIMARY KEY, ideia TEXT, tamanho_local TEXT, pagamento TEXT, consent TEXT, data TIMESTAMP)''')
    c.execute("INSERT OR REPLACE INTO clientes VALUES (?, ?, ?, ?, ?, ?)", 
              (from_number, ideia, tamanho_local, pagamento, consent, datetime.datetime.now()))
    conn.commit()
    conn.close()

# Atualizar consentimento no DB
def update_consent(from_number, consent):
    init_db()
    conn = sqlite3.connect('clientes.db')
    c = conn.cursor()
    c.execute("UPDATE clientes SET consentimento = ? WHERE numero = ?", (consent, from_number))
    conn.commit()
    conn.close()

# Salvar agendamento (SQLite)
def save_agendamento(from_number, data, dia, horario, tatuador):
    init_db()
    conn = sqlite3.connect('agenda.db')
    c = conn.cursor()
    c.execute("INSERT INTO agenda (dia, horario, numero, ideia, status) VALUES (?, ?, ?, ?, ?)",
              (dia, horario, from_number, data.get('ideia', ''), 'Pendente'))
    conn.commit()
    conn.close()

# Gerar slots disponíveis
def get_available_slots():
    dias = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado"]
    horarios = ["09:00", "10:00", "11:00", "14:00", "15:00", "16:00"]
    init_db()
    conn = sqlite3.connect('agenda.db')
    c = conn.cursor()
    c.execute("SELECT dia, horario FROM agenda")
    agendados = c.fetchall()
    conn.close()
    
    slots = []
    for dia in dias:
        for horario in horarios:
            if (dia, horario) not in agendados:
                slots.append(f"{dia} às {horario}")
    return slots[:5]  # Limita a 5 slots

# Visualizar agenda
def visualizar_agenda(com_indices=False):
    init_db()
    conn = sqlite3.connect('agenda.db')
    c = conn.cursor()
    c.execute("SELECT * FROM agenda")
    rows = c.fetchall()
    conn.close()
    
    if not rows:
        return "Nenhum agendamento encontrado."
    
    agenda = {}
    agendamentos_lista = []
    for row in rows:
        dia = row[1]
        if dia not in agenda:
            agenda[dia] = []
        info = f"{row[3]} - {row[2]} ({row[4]}) - Status: {row[5]}"
        agenda[dia].append(info)
        agendamentos_lista.append({
            'id': row[0], 'Dia': row[1], 'Horario': row[2], 'Numero': row[3], 'Ideia': row[4], 'Status': row[5]
        })
    
    if com_indices:
        result = "Agendamentos:\n"
        for i, ag in enumerate(agendamentos_lista):
            result += f"{i+1}. {ag['Dia']} às {ag['Horario']} - {ag['Numero']} ({ag['Ideia']}) - Status: {ag['Status']}\n"
        return result, agendamentos_lista
    
    result = "Agenda Semanal:\n"
    dias = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
    for dia in dias:
        result += f"\n{dia}:\n"
        if dia in agenda:
            result += "\n".join(agenda[dia]) + "\n"
        else:
            result += "Sem agendamentos\n"
    return result

# Remover agendamento
def remover_agendamento(indice, agendamentos_lista):
    if 0 <= indice < len(agendamentos_lista):
        id_to_remove = agendamentos_lista[indice]['id']
        init_db()
        conn = sqlite3.connect('agenda.db')
        c = conn.cursor()
        c.execute("DELETE FROM agenda WHERE id = ?", (id_to_remove,))
        conn.commit()
        conn.close()
        ag_removido = agendamentos_lista[indice]
        return f"Agendamento removido com sucesso:\n{ag_removido['Dia']} às {ag_removido['Horario']} - {ag_removido['Numero']} ({ag_removido['Ideia']}) - Status: {ag_removido['Status']}"
    return "Índice inválido."

# Salvar/load state (para persistência)
def save_state(from_number, state):
    init_db()
    conn = sqlite3.connect('agenda.db')  # Corrigido para agenda.db
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO conversations (numero, step, data) VALUES (?, ?, ?)",
              (from_number, state["step"], json.dumps(state.get("data", {}))))
    conn.commit()
    conn.close()

def load_state(from_number):
    init_db()
    conn = sqlite3.connect('agenda.db')  # Corrigido para agenda.db
    c = conn.cursor()
    c.execute("SELECT step, data FROM conversations WHERE numero = ?", (from_number,))
    row = c.fetchone()
    conn.close()
    if row:
        return {"step": row[0], "data": json.loads(row[1]) if row[1] else {}, "autenticado": row[1] and 'autenticado' in json.loads(row[1])}
    return {"step": 0, "data": {}, "autenticado": False}

@app.route("/", methods=["GET"])
def health_check():
    return "OK", 200

@app.route("/webhook", methods=["POST"])
def webhook():
    print(f"Recebido de {request.values.get('From', 'desconhecido')}: {request.values.get('Body', 'sem corpo')}")
    incoming_msg = request.values.get("Body", "").lower().strip()
    from_number = request.values.get("From")
    media_url = request.values.get("MediaUrl0", "")
    resp = MessagingResponse()

    try:
        # Opt-out para conformidade Meta
        if incoming_msg in ['pare', 'stop', 'cancelar', 'não']:
            save_state(from_number, {"step": 0, "data": {}, "autenticado": False})
            resp.message("Mensagens canceladas. Para reativar, envie 'oi'.")
            return str(resp)

        # Carrega state do DB
        state = load_state(from_number)

        # Verifica se é o tatuador
        if is_tatuador:
            print(f"Verificando autenticação para {from_number}. Senha recebida: '{incoming_msg}', TATUADOR_SENHA: '{TATUADOR_SENHA}'")
            print(f"Comparação: '{incoming_msg}' vs '{TATUADOR_SENHA.lower()}' - Estado: {state}")
            if not state.get("autenticado", False):
                if incoming_msg == TATUADOR_SENHA.lower().strip():  # Remove espaços e compara case-insensitive
                    state["autenticado"] = True
                    save_state(from_number, state)
                    resp.message("Acesso liberado! Digite 'ver agenda' para visualizar, 'adicionar agendamento' para incluir ou 'remover agendamento [número]'.")
                    return str(resp)
                else:
                    resp.message("Senha incorreta. Tente novamente.")
                    return str(resp)
            
            # Após autenticação, processa comandos
            if state.get("autenticado", False):
                if incoming_msg == "ver agenda":
                    agenda, agendamentos = visualizar_agenda(com_indices=True)
                    resp.message(agenda)
                    save_state(from_number, state)
                    return str(resp)
                elif incoming_msg.startswith("remover agendamento"):
                    try:
                        indice = int(incoming_msg.split()[-1]) - 1 if len(incoming_msg.split()) > 1 else -1
                        _, agendamentos = visualizar_agenda(com_indices=True)
                        mensagem = remover_agendamento(indice, agendamentos)
                        resp.message(mensagem)
                        save_state(from_number, state)
                    except (ValueError, IndexError):
                        resp.message("Índice inválido. Use 'remover agendamento [número]' após ver a agenda.")
                    return str(resp)

        # Fluxo do cliente
        if state["step"] == 0:
            resp.message("Olá! Bem-vindo ao Katami Studio! Você concorda em receber mensagens automáticas sobre orçamentos e agendamentos via WhatsApp? Responda 'Sim' para continuar ou 'Não' para cancelar.")
            state["step"] = 1
            save_state(from_number, state)
            return str(resp)

        elif state["step"] == 1:
            if incoming_msg.lower() in ['sim', 's', 'yes']:
                state["data"]["consent"] = "Sim"
                resp.message("Obrigado por confirmar! Qual é a ideia do seu desenho?")
                state["step"] = 2
            else:
                resp.message("Entendido! Não enviaremos mensagens. Envie 'oi' para reativar.")
                state["step"] = 0
                state["data"] = {}
            save_state(from_number, state)
            return str(resp)

        elif state["step"] == 2:
            state["data"]["ideia"] = incoming_msg
            resp.message("Legal! Qual o tamanho aproximado (em cm) e onde você quer tatuar?")
            state["step"] = 3
            save_state(from_number, state)
            return str(resp)

        elif state["step"] == 3:
            state["data"]["tamanho_local"] = incoming_msg
            resp.message("Como você prefere pagar?\n1️⃣ PIX\n2️⃣ Cartão\n3️⃣ Dinheiro")
            state["step"] = 4
            save_state(from_number, state)
            return str(resp)

        elif state["step"] == 4:
            if incoming_msg not in ['1', '2', '3']:
                resp.message("Por favor, digite 1, 2 ou 3.")
                return str(resp)
            state["data"]["pagamento"] = incoming_msg
            save_to_db(from_number, state["data"]["ideia"], state["data"]["tamanho_local"], state["data"]["pagamento"], state["data"]["consent"])
            tatuadores_msg = "Escolha o tatuador:\n"
            for key, tatuador in TATUADORES.items():
                tatuadores_msg += f"{key}. {tatuador['nome']} - {tatuador['estilo']}\n"
            resp.message(tatuadores_msg)
            state["step"] = 5
            save_state(from_number, state)
            return str(resp)

        elif state["step"] == 5:
            if incoming_msg not in TATUADORES:
                resp.message("Escolha inválida. Digite 1 ou 2.")
                return str(resp)
            state["data"]["tatuador"] = TATUADORES[incoming_msg]["nome"]
            resp.message("Por favor, envie uma imagem de referência para o seu desenho (opcional). Se não tiver, digite 'sem imagem'.")
            state["step"] = 6
            save_state(from_number, state)
            return str(resp)

        elif state["step"] == 6:
            if incoming_msg == "sem imagem":
                state["data"]["imagem"] = "Nenhuma imagem fornecida"
            elif media_url:
                state["data"]["imagem"] = media_url
            else:
                resp.message("Por favor, envie uma imagem ou digite 'sem imagem'.")
                return str(resp)
            client.messages.create(
                body=f"Solicitação de orçamento:\nCliente: {from_number}\nIdeia: {state['data']['ideia']}\nTamanho/Local: {state['data']['tamanho_local']}\nPagamento: {state['data']['pagamento']}\nTatuador: {state['data']['tatuador']}\nImagem de referência: {state['data']['imagem']}\nPor favor, responda com o valor do orçamento.",
                from_=BOT_NUMERO,
                to=TATUADOR_NUMERO
            )
            orcamento_requests[from_number] = from_number
            resp.message("Solicitei o orçamento ao tatuador. Aguarde a resposta!")
            state["step"] = 7
            save_state(from_number, state)
            return str(resp)

        elif state["step"] == 7:
            if incoming_msg in ['1', 'sim', 's', 'yes']:
                slots = get_available_slots()
                if not slots:
                    resp.message("Desculpe, não há horários disponíveis esta semana. Tente novamente mais tarde!")
                    state["step"] = 0
                    state["data"] = {}
                    save_state(from_number, state)
                    return str(resp)
                slots_message = "Escolha um horário para sua tatuagem:\n" + "\n".join(f"{i+1}. {slot}" for i, slot in enumerate(slots))
                resp.message(slots_message)
                state["slots"] = slots
                state["step"] = 8
            elif incoming_msg in ['2', 'não', 'n', 'no']:
                resp.message("Entendido! Obrigado pelo interesse. Envie 'oi' para reativar.")
                state["step"] = 0
                state["data"] = {}
                save_state(from_number, state)
            else:
                resp.message("Por favor, digite 1 para 'Sim' ou 2 para 'Não'.")
            return str(resp)

        elif state["step"] == 8:
            try:
                escolha = int(incoming_msg) - 1
                if 0 <= escolha < len(state["slots"]):
                    slot = state["slots"][escolha]
                    dia, horario = slot.split(" às ")
                    save_agendamento(from_number, state["data"], dia, horario, state["data"]["tatuador"])
                    resp.message(
                        f"Agendamento confirmado para {slot} com {state['data']['tatuador']}! Aqui está o que temos:\n"
                        f"- Ideia: {state['data']['ideia']}\n"
                        f"- Tamanho/Local: {state['data']['tamanho_local']}\n"
                        f"- Pagamento: {state['data']['pagamento']}\n"
                        f"- Orçamento: {state['data'].get('orcamento', 'Não informado')}\n"
                        "Obrigado por escolher o Katami Studio!"
                    )
                    client.messages.create(
                        body=f"Cliente confirmou o agendamento:\nCliente: {from_number}\nIdeia: {state['data']['ideia']}\nTamanho/Local: {state['data']['tamanho_local']}\nPagamento: {state['data']['pagamento']}\nAgendado para: {slot}\nTatuador: {state['data']['tatuador']}\nOrçamento: {state['data'].get('orcamento', 'Não informado')}\nImagem de referência: {state['data']['imagem']}",
                        from_=BOT_NUMERO,
                        to=TATUADOR_NUMERO
                    )
                    state["step"] = 0
                    state["data"] = {}
                    state.pop("slots", None)
                    save_state(from_number, state)
                else:
                    resp.message("Escolha inválida. Diga 'oi' para começar de novo.")
                    state["step"] = 0
                    state["data"] = {}
                    save_state(from_number, state)
            except ValueError:
                resp.message("Por favor, digite o número do horário. Diga 'oi' para começar de novo.")
                state["step"] = 0
                state["data"] = {}
                save_state(from_number, state)
            return str(resp)

        else:
            resp.message("Algo deu errado. Vamos começar de novo? Diga 'oi'!")
            state["step"] = 0
            state["data"] = {}
            save_state(from_number, state)
            return str(resp)

    except Exception as e:
        print(f"Erro geral: {e}")
        resp.message("Erro interno. Tente novamente mais tarde.")
        return str(resp)

# Rota para visualizar a agenda via web
@app.route("/agenda", methods=["GET"])
def get_agenda():
    return visualizar_agenda()

if __name__ == "__main__":
    init_db()  # Inicializa DB
    port = int(os.getenv("PORT", 5000))  # Usa 5000 como fallback
    app.run(host="0.0.0.0", port=port, debug=False)  # debug=False para produção
