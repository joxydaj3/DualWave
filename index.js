require('dotenv').config();
const { Telegraf, Markup, session } = require('telegraf');
const { Pool } = require('pg');
const http = require('http');

// Configuração do Bot e Banco de Dados
const bot = new Telegraf(process.env.BOT_TOKEN);
const pool = new Pool({
    connectionString: process.env.DATABASE_URL,
    ssl: { rejectUnauthorized: false }
});

const RATE = 70; // 1 USD = 70 MZN

// Traduções
const i18n = {
    pt: {
        start: "Bem-vindo ao DualWave! 🌊\nEscolha seu idioma:",
        main_menu: "Menu Principal",
        balance_btn: "💰 Saldo",
        invest_btn: "📈 Investir",
        team_btn: "👥 Equipe",
        wallet_btn: "💳 Carteira",
        lang_btn: "🇺🇸 English",
        balance_msg: (name, usd) => `👤 *Usuário:* ${name}\n\n💵 *Saldo Disponível:*\n${usd.toFixed(2)} USD\n${(usd * RATE).toFixed(2)} MZN`,
        select_plan: "Escolha um plano de investimento:",
        back: "⬅️ Voltar"
    },
    en: {
        start: "Welcome to DualWave! 🌊\nChoose your language:",
        main_menu: "Main Menu",
        balance_btn: "💰 Balance",
        invest_btn: "📈 Invest",
        team_btn: "👥 Team",
        wallet_btn: "💳 Wallet",
        lang_btn: "🇧🇷 Português",
        balance_msg: (name, usd) => `👤 *User:* ${name}\n\n💵 *Available Balance:*\n${usd.toFixed(2)} USD\n${(usd * RATE).toFixed(2)} MZN`,
        select_plan: "Choose an investment plan:",
        back: "⬅️ Back"
    }
};

// Middleware de Sessão e Idioma
bot.use(session());
bot.use(async (ctx, next) => {
    if (!ctx.from) return;
    try {
        const res = await pool.query("SELECT language FROM users WHERE id = $1", [ctx.from.id]);
        ctx.session = ctx.session || {};
        ctx.session.lang = res.rows[0]?.language || 'pt';
    } catch (err) {
        ctx.session.lang = 'pt';
    }
    return next();
});

// --- COMANDOS ---

// Comando /start
bot.command('start', async (ctx) => {
    const lang = ctx.session.lang;
    return ctx.reply(i18n[lang].start, Markup.inlineKeyboard([
        [Markup.button.callback("🇧🇷 Português", "set_pt"), Markup.button.callback("🇺🇸 English", "set_en")]
    ]));
});

// Callback para definir idioma
bot.action(/set_(pt|en)/, async (ctx) => {
    const lang = ctx.match[1];
    const userId = ctx.from.id;
    const refCode = Math.random().toString(36).substring(2, 8).toUpperCase();

    try {
        await pool.query(
            "INSERT INTO users (id, name, language, ref_code) VALUES ($1, $2, $3, $4) ON CONFLICT (id) DO UPDATE SET language = $3",
            [userId, ctx.from.first_name, lang, refCode]
        );
        ctx.session.lang = lang;
        ctx.answerCbQuery();
        return showMainMenu(ctx);
    } catch (err) {
        console.error(err);
        ctx.reply("Error connecting to database.");
    }
});

// Função para exibir Menu Principal
async function showMainMenu(ctx) {
    const lang = ctx.session.lang;
    const t = i18n[lang];
    return ctx.reply(`🌊 *DualWave ${t.main_menu}*`, Markup.keyboard([
        [t.balance_btn, t.invest_btn],
        [t.team_btn, t.wallet_btn],
        [t.lang_btn]
    ]).resize());
}

// Botão de Saldo
bot.hears([i18n.pt.balance_btn, i18n.en.balance_btn], async (ctx) => {
    const lang = ctx.session.lang;
    const res = await pool.query("SELECT balance_usd FROM users WHERE id = $1", [ctx.from.id]);
    const balance = res.rows[0]?.balance_usd || 0;
    
    return ctx.replyWithMarkdown(i18n[lang].balance_msg(ctx.from.first_name, balance));
});

// Botão de Investir (Exemplo de Planos)
bot.hears([i18n.pt.invest_btn, i18n.en.invest_btn], async (ctx) => {
    const lang = ctx.session.lang;
    // Aqui você buscaria os planos do Supabase (tabela 'plans')
    return ctx.reply(i18n[lang].select_plan, Markup.inlineKeyboard([
        [Markup.button.callback("Plano Alpha - 10 USD", "buy_alpha")],
        [Markup.button.callback("Plano Beta - 50 USD", "buy_beta")]
    ]));
});

// Troca de Idioma via Menu
bot.hears([i18n.pt.lang_btn, i18n.en.lang_btn], (ctx) => {
    ctx.session.lang = ctx.session.lang === 'pt' ? 'en' : 'pt';
    return showMainMenu(ctx);
});

// --- INICIALIZAÇÃO ---

bot.launch().then(() => console.log("DualWave Bot Online 🚀"));

// Servidor dummy para o Railway não matar o processo
http.createServer((req, res) => {
    res.write('Bot is running');
    res.end();
}).listen(process.env.PORT || 3000);

// Graceful stop
process.once('SIGINT', () => bot.stop('SIGINT'));
process.once('SIGTERM', () => bot.stop('SIGTERM'));
