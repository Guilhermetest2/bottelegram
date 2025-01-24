import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from time import sleep
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
import os
from dotenv import load_dotenv
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)
from concurrent.futures import ThreadPoolExecutor, as_completed

# Configuração do Telegram Bot
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

# Configurações do navegador Selenium
options = Options()
options.add_experimental_option("detach", True)
options.add_experimental_option("excludeSwitches", ["enable-logging"])
options.add_argument("--lang=pt-BR")
options.add_argument("--disable-notifications")
options.add_argument("--headless")  # Rodar em modo headless
options.add_argument("--disable-gpu")  # Desabilitar GPU (útil em headless)
options.add_argument("--no-sandbox")  # Útil no ambiente de servidores ou contêineres (por exemplo, Docker)
options.add_argument("--disable-software-rasterizer")  # Desabilitar o WebGL

# Estados da conversa
ORIGEM, DESTINO, DATA, PASSAGEIROS = range(4)

# Dicionário temporário para armazenar as respostas do usuário
user_data = {}

def buscar_passagens(voo_origem, voo_destino, voo_dia, voo_mes, qtd_adultos, qtd_criancas, qtd_bebes):
    from datetime import datetime
    
    voo_mes = int(voo_mes) - 1
    ano_atual = str(datetime.now().year)
    
    navegador = webdriver.Chrome(options=options)
    navegador.maximize_window()
    navegador.get("https://www.smiles.com.br/passagens")

    wait = WebDriverWait(navegador, 30)
    
    # Inserir origem
    origem = wait.until(EC.element_to_be_clickable((By.ID, 'inputOrigin')))
    origem.clear()
    origem.send_keys(voo_origem)
    sleep(3.0)
    origem.send_keys(Keys.TAB)

    # Inserir destino
    destino = wait.until(EC.element_to_be_clickable((By.ID, 'inputDestination')))
    destino.clear()
    destino.send_keys(voo_destino)
    sleep(3.0)
    destino.send_keys(Keys.TAB)

    # Selecionar somente ida
    selec_ida_volta = wait.until(EC.element_to_be_clickable((By.XPATH, '//*[@id="tripTypeSelectPosition1"]/div/div')))
    selec_ida_volta.click()
    sleep(3.0)
    ida = wait.until(EC.element_to_be_clickable((By.XPATH, '//*[@id="tripTypeSelectPosition1"]/div/div/div/ul/li[2]')))
    ida.click()

    # Escolher a data
    calendario = wait.until(EC.element_to_be_clickable((By.NAME, '_smilesflightsearchportlet_WAR_smilesbookingportlet_departure_date')))
    calendario.click()
    sleep(3.0)

    while True:
        meses = navegador.find_elements(By.XPATH, "//div[@id='ui-datepicker-div']//tbody//td[@class!=' ui-datepicker-unselectable ui-state-disabled ']")
        if any(mes.get_attribute("data-month") == str(voo_mes) and mes.get_attribute("data-year") == ano_atual for mes in meses):
            break
        seta_proximo_mes = navegador.find_element(By.XPATH, '//*[@id="ui-datepicker-div"]/div[2]/div/a')
        seta_proximo_mes.click()
        sleep(3.0)

    for data in meses:
        if data.get_attribute("data-month") == str(voo_mes) and data.get_attribute("data-year") == ano_atual:
            if voo_dia == "31":
                try:
                    data.click()
                    break
                except Exception as e:
                    print(f"Erro ao clicar no dia 31: {e}")
                    continue
            elif data.find_element(By.XPATH, "./a").text == voo_dia:
                data.click()
                break

    confirmar_btn = wait.until(EC.element_to_be_clickable((By.XPATH, '//*[@id="ui-datepicker-div"]/div[4]/button[1]')))
    confirmar_btn.click()

    # Adicionar passageiros
    try:
        for _ in range(qtd_adultos - 1):
            adicionar_adultos = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button.more[data-for='qtyAdults']")))
            adicionar_adultos.click()
            sleep(3.0)
    except Exception as e:
        print(f"Erro ao adicionar adultos: {str(e)}")

    for _ in range(qtd_criancas):
        adicionar_criancas = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button.more[data-for='qtyKids']")))
        adicionar_criancas.click()
        sleep(3.0)

    for _ in range(qtd_bebes):
        adicionar_bebes = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button.more[data-for='qtyBabies']")))
        adicionar_bebes.click()
        sleep(3.0)

    submit_btn = wait.until(EC.element_to_be_clickable((By.CLASS_NAME, 'btn-search-flight')))
    submit_btn.click()

    try:
        if voo_dia == "31":
            wait.until(EC.visibility_of_element_located((By.XPATH, '//*[@id="select-flight-accordion-ida"]/div[2]/div/div[5]/div[1]/div[1]/div[1]')))
        else:
            wait.until(EC.visibility_of_element_located((By.XPATH, '//*[@id="select-flight-accordion-ida"]/div[2]/div/div[5]/div[1]/div[1]/div[1]')))
    except TimeoutException:
        return [f"Sem passagens disponíveis para o dia {voo_dia}/{voo_mes}."]

    try:
        page_source = navegador.page_source
        site = BeautifulSoup(page_source, "html.parser")
        passagens = site.find_all("div", {"class": "select-flight-list-accordion-item"})

        if not passagens:
            raise ValueError("Nenhuma passagem encontrada na página.")

        data_viagem = f"{voo_dia}/{voo_mes + 1}/{ano_atual}"
        resultados = []
        for passagem in passagens:
            try:
                infoVoo_preco_milhas = passagem.find("label", {"class": "flight-fare-input-container-control-label", "for": "fare-item-SMILES_CLUB"})
                infoVoo_preco_milhas = infoVoo_preco_milhas.text if infoVoo_preco_milhas else "N/A"

                infoVoo_companhia = passagem.find("span", {"class": "company"})
                infoVoo_companhia = infoVoo_companhia.text if infoVoo_companhia else "N/A"

                infoVoo_info = passagem.find("div", {"class": "info"}).find_all("p")
                if infoVoo_info:
                    infoVoo_saida = infoVoo_info[1].text if len(infoVoo_info) > 1 else "N/A"
                    infoVoo_chegada = infoVoo_info[2].text if len(infoVoo_info) > 2 else "N/A"
                    infoVoo_cidade_inicio = (
                        infoVoo_info[3].text if len(infoVoo_info) > 3 else "N/A"
                    )
                    infoVoo_cidade_destino = (
                        infoVoo_info[4].text if len(infoVoo_info) > 4 else "N/A"
                    )
                else:
                    infoVoo_saida = infoVoo_chegada = infoVoo_cidade_inicio = infoVoo_cidade_destino = "N/A"

                resultados.append(
                    f"""
                    Data da Viagem: {data_viagem}
                    Companhia: {infoVoo_companhia}
                    Saindo de: {infoVoo_cidade_inicio}
                    Destino para: {infoVoo_cidade_destino}
                    Horário de saída: {infoVoo_saida}
                    Horário de chegada: {infoVoo_chegada}
                    Preço por milhas: {infoVoo_preco_milhas}
                    """
                )
            except Exception as e:
                print(f"Erro ao coletar dados de uma passagem: {e}")

        link = navegador.current_url
        resultados.append(f"\nClique aqui para acessar a pesquisa: [Clique aqui]({link})")



    except Exception as e:
        print(f"Erro geral ao coletar informações de passagens: {e}")
        resultados = [f"Erro ao coletar informações de passagens para o dia {voo_dia}/{voo_mes}."]

    finally:
        navegador.quit()

    return resultados



def buscar_passagens_mes(voo_origem, voo_destino, voo_mes, qtd_adultos, qtd_criancas, qtd_bebes):
    from calendar import monthrange
    from datetime import datetime

    ano_atual = datetime.now().year
    voo_mes = int(voo_mes)
    ultimo_dia = monthrange(ano_atual, voo_mes)[1]

    resultados_ida = []
    resultados_volta = []
    with ThreadPoolExecutor(max_workers=11) as executor:
        futures_ida = []
        futures_volta = []

        # Buscando passagens de ida
        for dia in range(1, ultimo_dia + 1):
            futures_ida.append(
                executor.submit(
                    buscar_passagens,
                    voo_origem,
                    voo_destino,
                    str(dia),
                    str(voo_mes),
                    qtd_adultos,
                    qtd_criancas,
                    qtd_bebes,
                )
            )

        # Buscando passagens de volta
        for dia in range(1, ultimo_dia + 1):
            futures_volta.append(
                executor.submit(
                    buscar_passagens,
                    voo_destino,  # Origem da volta
                    voo_origem,  # Destino da volta
                    str(dia),
                    str(voo_mes),
                    qtd_adultos,
                    qtd_criancas,
                    qtd_bebes,
                )
            )

        # Processar resultados de ida
        for future in as_completed(futures_ida):
            try:
                resultados_dia_ida = future.result()
                if resultados_dia_ida:
                    resultados_ida.extend(
                        [
                            r for r in resultados_dia_ida if "Preço por milhas" in r and "N/A" not in r
                        ]
                    )
            except Exception as e:
                resultados_ida.append(f"Erro ao buscar passagens de ida: {str(e)}")

        # Processar resultados de volta
        for future in as_completed(futures_volta):
            try:
                resultados_dia_volta = future.result()
                if resultados_dia_volta:
                    resultados_volta.extend(
                        [
                            r for r in resultados_dia_volta if "Preço por milhas" in r and "N/A" not in r
                        ]
                    )
            except Exception as e:
                resultados_volta.append(f"Erro ao buscar passagens de volta: {str(e)}")

    # Retornar resultados de ida e volta
    return resultados_ida, resultados_volta


# Adicionar novos estados para controle do fluxo
INICIO, NOVA_PESQUISA = range(4, 6)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bem-vindo! Deseja iniciar uma pesquisa por passagens? (Sim/Não)")
    return INICIO


async def inicio_pesquisa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    resposta = update.message.text.lower()
    if resposta in ["sim", "s"]:
        await update.message.reply_text("Ótimo! Vamos começar. Por favor, informe o código IATA do aeroporto de origem.")
        return ORIGEM
    elif resposta in ["não", "nao", "n"]:
        await update.message.reply_text("Ok, se precisar de algo, é só chamar!")
        return ConversationHandler.END
    else:
        await update.message.reply_text("Por favor, responda apenas com 'Sim' ou 'Não'. Deseja iniciar uma pesquisa?")
        return INICIO


async def origem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data["origem"] = update.message.text.upper()  # Garantir que o código seja em maiúsculas
    await update.message.reply_text("Agora, informe o código IATA do aeroporto de destino.")
    return DESTINO


async def destino(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data["destino"] = update.message.text.upper()  # Garantir que o código seja em maiúsculas
    await update.message.reply_text("Qual é o mês de partida? (Informe o número do mês de 1 a 12)")
    return DATA


async def data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mes_text = update.message.text.strip()

    if mes_text.isdigit() and 1 <= int(mes_text) <= 12:
        user_data["mes"] = mes_text
        await update.message.reply_text("Quantos passageiros adultos?")
        return PASSAGEIROS
    else:
        await update.message.reply_text("Por favor, informe um mês válido entre 1 e 12.")
        return DATA

# Adaptação para o handler de passageiros
import re

async def passageiros(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data["adultos"] = int(update.message.text)
    user_data["criancas"] = 0
    user_data["bebes"] = 0

    await update.message.reply_text("🔍 Buscando passagens de ida e volta para o mês inteiro...")

    try:
        # Buscar passagens
        resultados_ida, resultados_volta = buscar_passagens_mes(
            user_data["origem"],
            user_data["destino"],
            user_data["mes"],
            user_data["adultos"],
            user_data["criancas"],
            user_data["bebes"],
        )

        # Validar listas retornadas
        if not resultados_ida or not isinstance(resultados_ida, list):
            raise ValueError("Erro ao buscar passagens de ida: Nenhum resultado encontrado ou formato inválido.")
        if not resultados_volta or not isinstance(resultados_volta, list):
            raise ValueError("Erro ao buscar passagens de volta: Nenhum resultado encontrado ou formato inválido.")

        # Função para processar strings formatadas e extrair os dados
        def processar_passagens(lista_passagens):
            passagens_formatadas = []
            for passagem in lista_passagens:
                try:
                    # Usar regex para extrair informações
                    data = re.search(r"Data da Viagem:\s*(\d{1,2}/\d{1,2}/\d{4})", passagem)
                    preco = re.search(r"Preço por milhas:\s*([\d.,]+)", passagem)

                    # Verificar se os campos foram encontrados
                    if not data or not preco:
                        print(f"⚠️ Passagem com dados incompletos ignorada: {passagem}")
                        continue  # Ignorar e seguir para a próxima

                    # Converter os dados extraídos
                    data = data.group(1).strip()
                    preco = int(preco.group(1).replace(".", "").replace(",", ""))

                    # Adicionar passagem formatada
                    passagens_formatadas.append({"data": data, "preco": preco})
                except Exception as e:
                    print(f"Erro ao processar a passagem: {e}\nPassagem: {passagem}")
                    continue  # Ignorar e seguir para a próxima
            
            # Ordenar passagens pelo preço
            passagens_formatadas = sorted(passagens_formatadas, key=lambda x: x["preco"])
            return passagens_formatadas

        # Processar os dados de ida e volta
        try:
            resultados_ida = processar_passagens(resultados_ida)
        except Exception as e:
            raise ValueError(f"Erro ao buscar passagens de ida: {e}")
        try:
            resultados_volta = processar_passagens(resultados_volta)
        except Exception as e:
            raise ValueError(f"Erro ao buscar passagens de volta: {e}")

        # Filtrar as passagens mais baratas por dia
        def passagens_mais_baratas(resultados):
            mais_baratas_por_dia = {}
            for passagem in resultados:
                data = passagem["data"]
                preco = passagem["preco"]
                if data not in mais_baratas_por_dia or preco < mais_baratas_por_dia[data]["preco"]:
                    mais_baratas_por_dia[data] = passagem
            return list(mais_baratas_por_dia.values())

        resultados_ida = passagens_mais_baratas(resultados_ida)
        resultados_volta = passagens_mais_baratas(resultados_volta)

        # Função para dividir mensagens em blocos menores
        def dividir_mensagem(texto, limite=4000):
            linhas = texto.split("\n")
            blocos = []
            bloco_atual = ""
            for linha in linhas:
                if len(bloco_atual) + len(linha) + 1 > limite:
                    blocos.append(bloco_atual)
                    bloco_atual = ""
                bloco_atual += linha + "\n"
            if bloco_atual:
                blocos.append(bloco_atual)
            return blocos

        # Construir mensagem de ida
        mensagem_ida = f"✈️ **Passagens de Ida:** {user_data['origem']} ➡️ {user_data['destino']}\n\n"
        if resultados_ida:
            mensagem_ida += "🛫 **Mais baratas por dia:**\n"
            for passagem in resultados_ida:
                mensagem_ida += (
                    f"📅 Data: *{passagem['data']}*\n"
                    f"💰 Preço: *{passagem['preco']}* milhas\n"
                    "-----------------------------\n"
                )
        else:
            mensagem_ida += "❌ Nenhuma passagem encontrada.\n"

        # Construir mensagem de volta
        mensagem_volta = f"✈️ **Passagens de Volta:** {user_data['destino']} ➡️ {user_data['origem']}\n\n"
        if resultados_volta:
            mensagem_volta += "🛬 **Mais baratas por dia:**\n"
            for passagem in resultados_volta:
                mensagem_volta += (
                    f"📅 Data: *{passagem['data']}*\n"
                    f"💰 Preço: *{passagem['preco']}* milhas\n"
                    "-----------------------------\n"
                )
        else:
            mensagem_volta += "❌ Nenhuma passagem encontrada.\n"

        # Enviar mensagens em blocos
        for bloco in dividir_mensagem(mensagem_ida):
            await update.message.reply_text(bloco, parse_mode="Markdown")

        for bloco in dividir_mensagem(mensagem_volta):
            await update.message.reply_text(bloco, parse_mode="Markdown")

    except TimeoutException:
        await update.message.reply_text("⚠️ O tempo limite da busca foi excedido. Por favor, tente novamente.")
    except Exception as e:
        await update.message.reply_text(f"⚠️ Erro durante a busca: {str(e)}")

    await update.message.reply_text(
        "✅ Busca finalizada! Deseja iniciar uma nova pesquisa? (Sim/Não)"
    )
    return NOVA_PESQUISA


async def nova_pesquisa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    resposta = update.message.text.lower()
    if resposta in ["sim", "s"]:
        await update.message.reply_text("Ótimo! Vamos começar novamente. Por favor, informe o código IATA do aeroporto de origem.")
        return ORIGEM
    elif resposta in ["não", "nao", "n"]:
        await update.message.reply_text("Busca encerrada e não se esqueça de digitar /start para iniciar uma nova busca, até logo!")
        return ConversationHandler.END
    else:
        await update.message.reply_text("Por favor, responda apenas com 'Sim' ou 'Não'. Deseja iniciar uma nova pesquisa?")
        return NOVA_PESQUISA


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Busca cancelada.")
    return ConversationHandler.END


def main():
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Conversational Handler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            INICIO: [MessageHandler(filters.TEXT & ~filters.COMMAND, inicio_pesquisa)],
            ORIGEM: [MessageHandler(filters.TEXT & ~filters.COMMAND, origem)],
            DESTINO: [MessageHandler(filters.TEXT & ~filters.COMMAND, destino)],
            DATA: [MessageHandler(filters.TEXT & ~filters.COMMAND, data)],
            PASSAGEIROS: [MessageHandler(filters.TEXT & ~filters.COMMAND, passageiros)],
            NOVA_PESQUISA: [MessageHandler(filters.TEXT & ~filters.COMMAND, nova_pesquisa)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(conv_handler)

    application.run_polling()


if __name__ == "__main__":
    main()
