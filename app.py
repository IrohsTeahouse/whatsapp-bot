import csv
import os
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client

app = Flask(__name__)

# Credenciais do Twilio (via variáveis de ambiente no Render)
account_sid = os.getenv("ACfa19e582d008093dd7126de8f7c926eeID")
auth_token = os.getenv("3176d63e95798eba06e87ea446513e9e")
client = Client(account_sid, auth_token)

# Estado simples para acompanhar a conversa
conversations = {}
# Estado para rastrear solicitações de orçamento
orcamento_requests = {}

# Número do tatuador (substitua pelo seu número real)
TATUADOR_NUMERO = "whatsapp:+55S13991032680"
# Senha simples para autenticação do tatuador
TATUADOR_SENHA = "tatuador123"

# Descrição dos tatuadores
TATUADORES = {
    "1": {"nome": "Lucas", "estilo": "Especialista em realismo e tatuagens detalhadas, ideal para retratos e desenhos complexos."},
    "2": {"nome": "Mariana", "estilo": "Focada em aquarela e traços delicados, perfeita para tatuagens coloridas e artísticas."}
}

# Função para salvar os dados do cliente em clientes.csv
def save_to_csv(from_number, data, tatuador):
    file_exists = os.path.isfile('clientes.csv')
    with open('clientes.csv', mode='a', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        if not file_exists:
            writer.writerow(['Numero', 'Ideia', 'Tamanho_Local', 'Pagamento', 'Tatuador'])
        writer.writerow([from_number, data['ideia'], data['tamanho_local'], data['pagamento'], tatuador])

# Função para salvar agendamentos em agenda.csv
def save_agendamento(from_number, data, dia, horario, tatuador):
    file_exists = os.path.isfile('agenda.csv')
    with open('agenda.csv', mode='a', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        if not file_exists:
            writer.writerow(['Dia', 'Horario', 'Numero', 'Ideia', 'Tatuador'])
        writer.writerow([dia, horario, from_number, data['ideia'], tatuador])

# Função para gerar slots disponíveis (segunda a sábado, 9h-17h)
def get_available_slots():
    dias = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado"]
    horarios = ["09:00", "10:00", "11:00", "14:00", "15:00", "16:00"]
    agendados = []
    if os.path.isfile('agenda.csv'):
        with open('agenda.csv', mode='r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            for row in reader:
                agendados.append((row['Dia'], row['Horario']))
    
    slots = []
    for dia in dias:
        for horario in horarios:
            if (dia, horario) not in agendados:
                slots.append(f"{dia} às {horario}")
    return slots

# Função para visualizar a agenda com índices para remoção
def visualizar_agenda(com_indices=False):
    if not os.path.isfile('agenda.csv'):
        return "Nenhum agendamento encontrado."
    agenda = {}
    agendamentos_lista = []
    with open('agenda.csv', mode='r', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        for row in reader:
            dia = row['Dia']
            if dia not in agenda:
                agenda[dia] = []
            info = f"{row['Horario']} - {row['Numero']} ({row['Ideia']}) - Tatuador: {row['Tatuador']}"
            agenda[dia].append(info)
            agendamentos_lista.append({
                'Dia': dia,
                'Horario': row['Horario'],
                'Numero': row['Numero'],
                'Ideia': row['Ideia'],
                'Tatuador': row['Tatuador']
            })
    
    if com_indices:
        result = "Agendamentos:\n"
        for i, agendamento in enumerate(agendamentos_lista):
            result += (f"{i+1}. {agendamento['Dia']} às {agendamento['Horario']} - "
                      f"{agendamento['Numero']} ({agendamento['Ideia']}) - Tatuador: {agendamento['Tatuador']}\n")
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

# Função para remover um agendamento
def remover_agendamento(indice, agendamentos_lista):
    if 0 <= indice < len(agendamentos_lista):
        agendamento_removido = agendamentos_lista.pop(indice)
        # Regravar agenda.csv sem o agendamento removido
        with open('agenda.csv', mode='w', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            writer.writerow(['Dia', 'Horario', 'Numero', 'Ideia', 'Tatuador'])
            for agendamento in agendamentos_lista:
                writer.writerow([
                    agendamento['Dia'],
                    agendamento['Horario'],
                    agendamento['Numero'],
                    agendamento['Ideia'],
                    agendamento['Tatuador']
                ])
        return (f"Agendamento removido com sucesso:\n"
                f"{agendamento_removido['Dia']} às {agendamento_removido['Horario']} - "
                f"{agendamento_removido['Numero']} ({agendamento_removido['Ideia']}) - "
                f"Tatuador: {agendamento_removido['Tatuador']}")
    return "Índice inválido."

@app.route("/webhook", methods=["POST"])
def webhook():
    incoming_msg = request.values.get("Body", "").lower()
    from_number = request.values.get("From")
    media_url = request.values.get("MediaUrl0")  # Obtém o URL da imagem, se enviada
    resp = MessagingResponse()

    # Verifica se é o tatuador
    is_tatuador = from_number == TATUADOR_NUMERO

    # Inicializa o estado da conversa, se não existir
    if from_number not in conversations:
        conversations[from_number] = {"step": 0, "data": {}, "autenticado": False}

    state = conversations[from_number]

    # Comandos do tatuador
    if is_tatuador:
        # Autenticação
        if not state["autenticado"]:
            if incoming_msg == TATUADOR_SENHA:
                state["autenticado"] = True
                resp.message("Acesso liberado! Digite 'ver agenda' para visualizar a agenda, "
                            "'adicionar agendamento' para incluir um novo ou 'remover agendamento' para excluir um.")
            else:
                resp.message("Digite a senha para acessar as funcionalidades de tatuador.")
            return str(resp)

        # Verificar se a mensagem do tatuador é um orçamento
        if state["step"] == 0 and from_number in orcamento_requests:
            cliente_numero = orcamento_requests[from_number]
            cliente_state = conversations[cliente_numero]
            cliente_state["data"]["orcamento"] = incoming_msg
            # Enviar mensagem ao cliente perguntando se aceita o orçamento
            resp.message(f"O tatuador informou o orçamento: {incoming_msg}. Você aceita?\n1️⃣ Sim\n2️⃣ Não")
            cliente_state["step"] = 6
            del orcamento_requests[from_number]
            return str(resp)

        # Comandos após autenticação
        if incoming_msg == "ver agenda":
            agenda = visualizar_agenda()
            resp.message(agenda)
            return str(resp)
        elif incoming_msg == "adicionar agendamento":
            resp.message("Digite o dia (ex.: Segunda) e o horário (ex.: 09:00) no formato 'Dia Horário'.")
            state["step"] = "adicionar_agendamento_1"
            return str(resp)
        elif incoming_msg == "remover agendamento":
            lista_msg, agendamentos_lista = visualizar_agenda(com_indices=True)
            if "Nenhum agendamento encontrado" in lista_msg:
                resp.message(lista_msg)
            else:
                resp.message(f"{lista_msg}\nDigite o número do agendamento que deseja remover.")
                state["agendamentos_lista"] = agendamentos_lista
                state["step"] = "remover_agendamento"
            return str(resp)
        elif state["step"] == "remover_agendamento":
            try:
                indice = int(incoming_msg) - 1
                resultado = remover_agendamento(indice, state["agendamentos_lista"])
                resp.message(resultado)
                state["step"] = 0
                state.pop("agendamentos_lista", None)
            except ValueError:
                resp.message("Por favor, digite um número válido. Digite 'remover agendamento' para tentar novamente.")
            return str(resp)
        elif state["step"] == "adicionar_agendamento_1":
            try:
                dia, horario = incoming_msg.split()
                dias_validos = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado"]
                horarios_validos = ["09:00", "10:00", "11:00", "14:00", "15:00", "16:00"]
                dia = dia.capitalize()
                if dia.lower() not in dias_validos or horario not in horarios_validos:
                    raise ValueError
                state["data"]["dia"] = dia
                state["data"]["horario"] = horario
                resp.message("Digite o número do cliente (ex.: whatsapp:+5511999999999).")
                state["step"] = "adicionar_agendamento_2"
            except ValueError:
                resp.message("Formato inválido. Digite no formato 'Dia Horário' (ex.: Segunda 09:00).")
            return str(resp)
        elif state["step"] == "adicionar_agendamento_2":
            if not incoming_msg.startswith("whatsapp:+"):
                resp.message("Número inválido. Deve começar com 'whatsapp:+'. Tente novamente.")
                return str(resp)
            state["data"]["numero"] = incoming_msg
            resp.message("Qual é a ideia do desenho do cliente?")
            state["step"] = "adicionar_agendamento_3"
            return str(resp)
        elif state["step"] == "adicionar_agendamento_3":
            state["data"]["ideia"] = incoming_msg
            # Perguntar qual tatuador
            tatuadores_msg = "Escolha o tatuador:\n"
            for key, tatuador in TATUADORES.items():
                tatuadores_msg += f"{key}. {tatuador['nome']} - {tatuador['estilo']}\n"
            resp.message(tatuadores_msg)
            state["step"] = "adicionar_agendamento_4"
            return str(resp)
        elif state["step"] == "adicionar_agendamento_4":
            if incoming_msg not in TATUADORES:
                resp.message("Escolha inválida. Digite o número do tatuador (1 ou 2).")
                return str(resp)
            tatuador = TATUADORES[incoming_msg]["nome"]
            save_agendamento(
                state["data"]["numero"],
                state["data"],
                state["data"]["dia"],
                state["data"]["horario"],
                tatuador
            )
            resp.message(
                f"Agendamento adicionado com sucesso!\n"
                f"Dia: {state['data']['dia']}\n"
                f"Horário: {state['data']['horario']}\n"
                f"Cliente: {state['data']['numero']}\n"
                f"Ideia: {state['data']['ideia']}\n"
                f"Tatuador: {tatuador}"
            )
            state["step"] = 0
            state["data"] = {}
            return str(resp)

    # Fluxo normal do cliente
    if state["step"] == 0:
        resp.message("Olá! Bem-vindo(a) ao estúdio de tatuagem! Qual é a ideia do seu desenho?")
        state["step"] = 1
    elif state["step"] == 1:
        state["data"]["ideia"] = incoming_msg
        resp.message("Legal! Qual o tamanho aproximado (em cm) e onde você quer tatuar?")
        state["step"] = 2
    elif state["step"] == 2:
        state["data"]["tamanho_local"] = incoming_msg
        resp.message("Como você prefere pagar?\n1️⃣ PIX\n2️⃣ Cartão\n3️⃣ Dinheiro")
        state["step"] = 3
    elif state["step"] == 3:
        state["data"]["pagamento"] = incoming_msg
        save_to_csv(from_number, state["data"], tatuador=None)  # Salva sem tatuador por enquanto
        # Perguntar qual tatuador o cliente deseja
        tatuadores_msg = "Escolha o tatuador:\n"
        for key, tatuador in TATUADORES.items():
            tatuadores_msg += f"{key}. {tatuador['nome']} - {tatuador['estilo']}\n"
        resp.message(tatuadores_msg)
        state["step"] = 4
    elif state["step"] == 4:
        if incoming_msg not in TATUADORES:
            resp.message("Escolha inválida. Digite o número do tatuador (1 ou 2).")
            return str(resp)
        tatuador = TATUADORES[incoming_msg]["nome"]
        state["data"]["tatuador"] = tatuador
        # Atualizar clientes.csv com o tatuador escolhido
        with open('clientes.csv', mode='r', encoding='utf-8') as file:
            lines = list(csv.reader(file))
        with open('clientes.csv', mode='w', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            writer.writerow(lines[0])  # Escrever o cabeçalho
            for line in lines[1:]:
                if line[0] == from_number and line[4] == "":
                    line[4] = tatuador
                writer.writerow(line)
        # Solicitar imagem de referência
        resp.message("Por favor, envie uma imagem de referência para o seu desenho (opcional). Se não tiver, digite 'sem imagem'.")
        state["step"] = 5
        return str(resp)
    elif state["step"] == 5:
        if incoming_msg == "sem imagem":
            state["data"]["imagem"] = "Nenhuma imagem fornecida"
        elif media_url:
            state["data"]["imagem"] = media_url
        else:
            resp.message("Por favor, envie uma imagem ou digite 'sem imagem'.")
            return str(resp)
        # Enviar solicitação de orçamento ao tatuador
        client.messages.create(
            body=f"Solicitação de orçamento:\nCliente: {from_number}\nIdeia: {state['data']['ideia']}\nTamanho/Local: {state['data']['tamanho_local']}\nPagamento: {state['data']['pagamento']}\nTatuador: {state['data']['tatuador']}\nImagem de referência: {state['data']['imagem']}\nPor favor, responda com o valor do orçamento.",
            from_="whatsapp:+14155238886",
            to="whatsapp:+55S13991032680"
        )
        orcamento_requests[from_number] = from_number
        resp.message("Solicitei o orçamento ao tatuador. Aguarde a resposta para prosseguir!")
        return str(resp)
    elif state["step"] == 6:
        if incoming_msg == "1":
            # Mostrar slots disponíveis para agendamento
            slots = get_available_slots()
            if not slots:
                resp.message("Desculpe, não há horários disponíveis esta semana. Tente novamente mais tarde!")
                state["step"] = 0
                state["data"] = {}
            else:
                slots_message = "Escolha um horário para sua tatuagem:\n" + "\n".join(f"{i+1}. {slot}" for i, slot in enumerate(slots[:5]))
                resp.message(slots_message)
                state["slots"] = slots
                state["step"] = 7
        elif incoming_msg == "2":
            resp.message("Entendido! Obrigado pelo interesse. Se precisar de algo, é só dizer 'oi' novamente!")
            state["step"] = 0
            state["data"] = {}
        else:
            resp.message("Por favor, digite 1 para 'Sim' ou 2 para 'Não'.")
        return str(resp)
    elif state["step"] == 7:
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
                    f"- Orçamento: {state['data']['orcamento']}\n"
                    "Obrigado por escolher nosso estúdio!"
                )
                client.messages.create(
                    body=f"Cliente confirmou o agendamento:\nCliente: {from_number}\nIdeia: {state['data']['ideia']}\nTamanho/Local: {state['data']['tamanho_local']}\nPagamento: {state['data']['pagamento']}\nAgendado para: {slot}\nTatuador: {state['data']['tatuador']}\nOrçamento: {state['data']['orcamento']}\nImagem de referência: {state['data']['imagem']}",
                    from_="whatsapp:+14155238886",
                    to="whatsapp:+55S13991032680"
                )
            else:
                resp.message("Escolha inválida. Diga 'oi' para começar de novo.")
        except ValueError:
            resp.message("Por favor, digite o número do horário. Diga 'oi' para começar de novo.")
        state["step"] = 0
        state["data"] = {}
        state.pop("slots", None)
        return str(resp)
    else:
        resp.message("Algo deu errado. Vamos começar de novo? Diga 'oi'!")

    return str(resp)

# Rota para visualizar a agenda via web
@app.route("/agenda", methods=["GET"])
def get_agenda():
    return visualizar_agenda()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
