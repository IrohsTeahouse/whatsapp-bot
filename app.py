from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
import os

app = Flask(__name__)

# Credenciais do Twilio (via variáveis de ambiente no Render)
account_sid = os.getenv("ACfa19e582d008093dd7126de8f7c926eeID")
auth_token = os.getenv("3176d63e95798eba06e87ea446513e9e")
client = Client(account_sid, auth_token)

# Estado simples para acompanhar a conversa
conversations = {}

@app.route("/webhook", methods=["POST"])
def webhook():
    incoming_msg = request.values.get("Body", "").lower()
    from_number = request.values.get("From")
    resp = MessagingResponse()

    # Inicializa o estado da conversa, se não existir
    if from_number not in conversations:
        conversations[from_number] = {"step": 0, "data": {}}

    state = conversations[from_number]

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
        resp.message(f"Entendido! Aqui está o que temos:\n- Ideia: {state['data']['ideia']}\n- Tamanho/Local: {state['data']['tamanho_local']}\n- Pagamento: {state['data']['pagamento']}\nVou passar pro tatuador!")
        # Envia para o tatuador
        client.messages.create(
            body=f"Novo cliente: {from_number}\nIdeia: {state['data']['ideia']}\nTamanho/Local: {state['data']['tamanho_local']}\nPagamento: {state['data']['pagamento']}",
            from_="whatsapp:+14155238886",  # Número do Sandbox
            to="whatsapp:+55S13991032680"  # Substitua pelo seu número
        )
        # Reseta a conversa
        state["step"] = 0
        state["data"] = {}
    else:
        resp.message("Algo deu errado. Vamos começar de novo? Diga 'oi'!")

    return str(resp)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
