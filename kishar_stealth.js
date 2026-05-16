const puppeteer = require('puppeteer-extra');
const StealthPlugin = require('puppeteer-extra-plugin-stealth');
puppeteer.use(StealthPlugin());

async function run() {
  console.log("🚀 INICIANDO KISHAR STEALTH ENGINE...");
  
  const browser = await puppeteer.launch({
    headless: false,
    userDataDir: './user_data',
    args: [
      '--no-sandbox',
      '--disable-setuid-sandbox',
      '--disable-infobars',
      '--window-position=0,0',
      '--window-size=1280,800',
      '--no-first-run',
      '--no-default-browser-check',
      '--disable-session-crashed-bubble',
      '--disable-features=ProfilePicker',
      '--profile-directory=Default'
    ]
  });

  const page = await browser.newPage();
  
  // Anti-bloqueo: Cerrar popups de "Restore" si aparecen (vía argumentos arriba)
  
  console.log("🔗 Navegando a Binance Login...");
  await page.goto('https://www.binance.com/en/login', { waitUntil: 'networkidle2' });
  
  // Intentar login automático
  try {
    const email = "victorhugovillegas1978@gmail.com";
    const pass = "Ukumari_1980";

    console.log("📝 Introduciendo credenciales...");
    await page.waitForSelector('input[name="email"]', { timeout: 10000 });
    await page.type('input[name="email"]', email, { delay: 100 });
    
    // Siguiente (puede ser un botón o Enter)
    await page.keyboard.press('Enter');
    
    await new Promise(r => setTimeout(r, 3000)); // Esperar transicion
    
    await page.waitForSelector('input[name="password"]', { timeout: 10000 });
    await page.type('input[name="password"]', pass, { delay: 100 });
    await page.keyboard.press('Enter');
    
    console.log("⏳ Esperando pantalla de MFA (Código de correo)...");
    // Aquí el bot esperaría a que aparezca el campo de código
    // Para una automatización real, abriríamos otra pestaña a Gmail u/1
    
    console.log("🔓 Por favor, si aparece el código de Binance, yo lo buscaré en tu Gmail.");
    
    // Crear segunda pestaña para Gmail
    const gmailPage = await browser.newPage();
    console.log("📬 Abriendo Gmail para capturar código...");
    await gmailPage.goto('https://mail.google.com/mail/u/1/#inbox', { waitUntil: 'networkidle2' });
    
    // El script se mantiene abierto para que el usuario vea el progreso
    console.log("👁️ Navegador abierto. El sistema está operando en modo Stealth.");
    
  } catch (error) {
    console.log("⚠️ Error en el flujo automático: " + error.message);
    console.log("👉 Por favor, completa el login manualmente en la ventana abierta.");
    console.log("La ventana se mantendrá abierta indefinidamente para que puedas operar. Ciérrala manualmente cuando termines.");
  }
  
  // Mantener el navegador abierto indefinidamente
  await new Promise(() => {});
}

run();
