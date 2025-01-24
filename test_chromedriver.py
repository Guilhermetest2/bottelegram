from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options

# Defina explicitamente o caminho para o ChromeDriver
chrome_options = Options()
chrome_options.add_argument('--headless')  # Roda sem a interface gráfica

# Aponte para o ChromeDriver em /usr/local/bin
service = Service("/usr/local/bin/chromedriver")
driver = webdriver.Chrome(service=service, options=chrome_options)

# Acesse o Google
driver.get("https://www.google.com")

# Exibe o título da página
print(driver.title)

# Finalize
driver.quit()
