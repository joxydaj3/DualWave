require('dotenv').config();
const { Telegraf, Markup, session } = require('telegraf');
const { Pool } = require('pg');
const texts = require('./translations');

// Configurações
const bot = new Telegraf(process.env.BOT_TOKEN);
const pool = new Pool({ connectionString: process.env.DATABASE_URL, ssl: { rejectUnauthorized: false } });
const RATE = 70; // 1 USD = 70 MZN

// Middleware de Sessão e Idioma
bot.use(session());
bot.use(async (ctx, next) => {
    if (!ctx.from) return;
    if (!ctx.session) ctx.session = {};
    
    const res = await pool.query("SELECT language FROM users WHERE id = $1", [ctx.from.id]);
    ctx.session.lang = res.rows[0]?.language || 'pt';
    return next();
});

// Formatação de Moeda Dual
const formatCurrency = (usd) => {
    const mzn = usd * RATE;
    return `${usd.toFixed(2)} USD ~ ${mzn.toFixed(2)} MZN`;
};

// Comando Inicial
bot.start(async (ctx) => {
    const res = await pool.query("SELECT * FROM users WHERE id = $1", [ctx.from.id]);
    
    if (res.rows.length === 0) {
        return ctx.reply("Choose language / Escolha o idioma:", Markup.inlineKeyboard([
            [Markup.button.callback("🇺🇸 English", "set_lang_en"), Markup.button.callback("🇲🇿 Português", "set_lang_pt")]
        ]));
    }
    return mainMenu(ctx);
});

// Registro de Idioma e Contato
bot.action(/set_lang_(.+)/, async (ctx) => {
    const lang = ctx.match[1];
    ctx.session.lang = lang;
    const refCode = Math.random().toString(36).substring(2, 8).toUpperCase();
    
    await pool.query(
        "INSERT INTO users (id, name, ref_code, language) VALUES ($1, $2, $3, $4) ON CONFLICT (id) DO UPDATE SET language = $4",
        [ctx.from.id, ctx.from.first_name, refCode, lang]
    );

    ctx.reply(texts[lang].no_phone, Markup.keyboard([
        [Markup.button.contactRequest(texts[lang].btn_contact)]
    ]).resize());
});

bot.on('contact', async (ctx) => {
    const phone = ctx.message.contact.phone_number;
    const lang = ctx.session.lang;
    await pool.query("UPDATE users SET phone = $1 WHERE id = $2", [phone, ctx.from.id]);
    ctx.reply("✅ Registro concluído!", Markup.removeKeyboard());
    mainMenu(ctx);
});

// Menu Principal
async function mainMenu(ctx) {
    const lang = ctx.session.lang;
    const t = texts[lang];
    ctx.reply("DualWave🌊", Markup.keyboard([
        [t.balance, t.invest],
        [t.team, t.wallet],
        [t.checkin, t.support]
    ]).resize());
}

// Lógica de Saldo
bot.hears([texts.pt.balance, texts.en.balance], async (ctx) => {
    const res = await pool.query("SELECT * FROM users WHERE id = $1", [ctx.from.id]);
    const u = res.rows[0];
    const lang = ctx.session.lang;
    ctx.reply(texts[lang].stats(u.balance_usd, u.balance_usd * RATE, u.name));
});

// Lógica de Investimento (Planos)
bot.hears([texts.pt.invest, texts.en.invest], async (ctx) => {
    const plans = await pool.query("SELECT * FROM plans ORDER BY price_usd ASC");
    let msg = ctx.session.lang === 'pt' ? "📈 Escolha um plano:\n\n" : "📈 Choose a plan:\n\n";
    
    const buttons = plans.rows.map(p => [
        Markup.button.callback(`${p.name} - ${p.price_usd} USD`, `buy_${p.id}`)
    ]);
    
    ctx.reply(msg, Markup.inlineKeyboard(buttons));
});

bot.action(/buy_(.+)/, async (ctx) => {
    const planId = ctx.match[1];
    const userId = ctx.from.id;
    const lang = ctx.session.lang;

    const u = (await pool.query("SELECT balance_usd FROM users WHERE id = $1", [userId])).rows[0];
    const p = (await pool.query("SELECT * FROM plans WHERE id = $1", [planId])).rows[0];

    if (u.balance_usd < p.price_usd) return ctx.answerCbQuery(texts[lang].insufficient, { show_alert: true });

    await pool.query("BEGIN");
    await pool.query("UPDATE users SET balance_usd = balance_usd - $1 WHERE id = $2", [p.price_usd, userId]);
    const expires = new Date(); expires.setDate(expires.getDate() + p.duration);
    await pool.query("INSERT INTO user_plans (user_id, plan_id, expires_at) VALUES ($1, $2, $3)", [userId, planId, expires]);
    await pool.query("COMMIT");

    ctx.reply(texts[lang].buy_success);
});

// Suporte
bot.hears([texts.pt.support, texts.en.support], (ctx) => {
    const msg = ctx.session.lang === 'pt' ? "🎧 Suporte DualWave:\nContato: @seu_usuario" : "🎧 DualWave Support:\nContact: @your_user";
    ctx.reply(msg);
});

// Sistema de Check-in
bot.hears([texts.pt.checkin, texts.en.checkin], async (ctx) => {
    const today = new Date().toISOString().split('T')[0];
    const u = (await pool.query("SELECT last_checkin FROM users WHERE id = $1", [ctx.from.id])).rows[0];
    
    if (u.last_checkin && u.last_checkin.toISOString().split('T')[0] === today) {
        return ctx.reply("❌ Já coletado hoje!");
    }

    const bonus = 0.50; // USD
    await pool.query("UPDATE users SET balance_usd = balance_usd + $1, last_checkin = $2 WHERE id = $3", [bonus, today, ctx.from.id]);
    ctx.reply(`🎁 Check-in: +${formatCurrency(bonus)}`);
});

// Inicialização
bot.launch();
console.log("DualWave Bot is running...");

// Tratamento de erros
process.once('SIGINT', () => bot.stop('SIGINT'));
process.once('SIGTERM', () => bot.stop('SIGTERM'));
