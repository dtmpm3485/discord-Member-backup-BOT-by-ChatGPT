// GPT_Memberbackup.js
require('dotenv').config();
const express = require('express');
const sqlite3 = require('sqlite3').verbose();
const axios = require('axios');
const { Client, GatewayIntentBits, EmbedBuilder, ActionRowBuilder, ButtonBuilder, ButtonStyle, PermissionsBitField } = require('discord.js');
const { REST } = require('@discordjs/rest');
const { Routes } = require('discord-api-types/v10');
const cron = require('node-cron');

const {
  CLIENT_ID,
  CLIENT_SECRET,
  REDIRECT_URI,
  Token: BOT_TOKEN,
} = process.env;

const DATABASE_FILE = './database.db';
const PORT = 5000; //ポート

// Discordクライアント
const client = new Client({
  intents: [
    GatewayIntentBits.Guilds,
    GatewayIntentBits.GuildMembers,
  ],
});

// SQLite
const db = new sqlite3.Database(DATABASE_FILE, (err) => {
  if (err) {
    console.error('Database connection error:', err);
  } else {
    console.log('Connected to SQLite database');
    initDatabase();
  }
});

function initDatabase() {
  db.serialize(() => {
    db.run(`
      CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        access_token TEXT,
        refresh_token TEXT
      )
    `);

    db.run(`
      CREATE TABLE IF NOT EXISTS call_limit (
        user_id TEXT PRIMARY KEY,
        last_call INTEGER
      )
    `);
  });
}

// Expressサーバー
const app = express();
app.use(express.urlencoded({ extended: true }));

const SUCCESS_HTML = `
<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>認証完了</title>
  <style>
    body {
      margin:0;
      height:100vh;
      display:flex;
      justify-content:center;
      align-items:center;
      background:linear-gradient(135deg, #ff9ecb, #7a57ff);
      font-family: "Segoe UI", Arial, sans-serif;
      color:#fff;
      overflow:hidden;
    }

    /* 背景の光の粒子アニメ */
    .bg-particle {
      position:absolute;
      width:200vmax;
      height:200vmax;
      background:radial-gradient(circle, rgba(255,255,255,0.25) 0%, rgba(255,255,255,0) 60%);
      animation: rotate 18s linear infinite;
      opacity:0.6;
    }
    @keyframes rotate {
      from { transform:rotate(0deg); }
      to { transform:rotate(360deg); }
    }

    .container {
      position:relative;
      padding:3rem 3.5rem;
      border-radius:30px;
      backdrop-filter: blur(25px);
      background:rgba(255,255,255,0.15);
      border:1px solid rgba(255,255,255,0.25);
      box-shadow:0 15px 40px rgba(0,0,0,0.25);
      text-align:center;
      animation: fadeIn 0.8s ease-out;
    }

    @keyframes fadeIn {
      from { transform:translateY(20px); opacity:0; }
      to { transform:translateY(0); opacity:1; }
    }

    .icon {
      font-size:3.5rem;
      margin-bottom:1rem;
      background:linear-gradient(145deg, #ffffff, #d1d1ff);
      width:80px;
      height:80px;
      display:flex;
      justify-content:center;
      align-items:center;
      border-radius:20px;
      color:#6a3cff;
      font-weight:bold;
      box-shadow: 
        inset 3px 3px 6px rgba(0,0,0,0.1),
        inset -3px -3px 6px rgba(255,255,255,0.6),
        0 8px 20px rgba(128,66,255,0.3);
    }

    h1 {
      font-size:1.9rem;
      line-height:1.6;
      margin:0;
      margin-top:0.8rem;
      letter-spacing:1px;
      text-shadow:0 0 10px rgba(0,0,0,0.15);
    }

    .highlight {
      padding:4px 10px;
      border-radius:8px;
      background:linear-gradient(135deg, #e0d4ff, #b693ff);
      color:#4b1fc4;
      font-weight:bold;
      box-shadow: 
        inset 2px 2px 5px rgba(255,255,255,0.7),
        inset -2px -2px 5px rgba(0,0,0,0.05);
    }
  </style>
</head>
<body>

  <div class="bg-particle"></div>

  <div class="container">
    <div class="icon">✓</div>
    <h1><span class="highlight">{{username}}</span> さんへ<br>ロールを付与しました！</h1>
  </div>
</body>
</html>
`;

// トークンリフレッシュ（全ユーザー）
async function refreshAllTokens() {
  console.log('[CRON] Refreshing all access tokens...');

  db.all('SELECT id, refresh_token FROM users', async (err, rows) => {
    if (err) return console.error(err);

    for (const { id, refresh_token } of rows) {
      if (!refresh_token) {
        db.run('DELETE FROM users WHERE id = ?', [id]);
        continue;
      }

      try {
        const response = await axios.post(
          'https://discord.com/api/oauth2/token',
          new URLSearchParams({
            client_id: CLIENT_ID,
            client_secret: CLIENT_SECRET,
            grant_type: 'refresh_token',
            refresh_token,
          }).toString(),
          {
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
          }
        );

        const { access_token, refresh_token: new_refresh = refresh_token } = response.data;

        db.run(
          'UPDATE users SET access_token = ?, refresh_token = ? WHERE id = ?',
          [access_token, new_refresh, id]
        );
      } catch (e) {
        console.error(`Failed to refresh token for user ${id}:`, e.response?.data || e.message);
        db.run('DELETE FROM users WHERE id = ?', [id]);
      }
    }
  });
}

// メンバー追加を試みる
async function addGuildMember(guildId, userId, accessToken) {
  try {
    const response = await axios.put(
      `https://discord.com/api/guilds/${guildId}/members/${userId}`,
      { access_token: accessToken },
      {
        headers: {
          Authorization: `Bot ${BOT_TOKEN}`,
          'Content-Type': 'application/json',
        },
      }
    );
    return response.status;
  } catch (error) {
    return error.response?.status || 500;
  }
}

// OAuthコールバック
app.get('/backup_member', async (req, res) => {
  const { code, state } = req.query;
  if (!code || !state) return res.status(400).send('Bad Request');

  let guildId, roleId;
  try {
    [guildId, roleId] = state.toString().split(':');
  } catch {
    return res.status(400).send('Invalid State');
  }

  try {
    // アクセストークン取得
    const tokenResponse = await axios.post(
      'https://discord.com/api/oauth2/token',
      new URLSearchParams({
        client_id: CLIENT_ID,
        client_secret: CLIENT_SECRET,
        grant_type: 'authorization_code',
        code,
        redirect_uri: REDIRECT_URI,
      }).toString(),
      { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } }
    );

    const { access_token, refresh_token } = tokenResponse.data;

    // ユーザー情報取得
    const userResponse = await axios.get('https://discord.com/api/users/@me', {
      headers: { Authorization: `Bearer ${access_token}` },
    });

    const { id, username } = userResponse.data;

    // DB保存
    db.run(
      `INSERT OR REPLACE INTO users (id, access_token, refresh_token) VALUES (?, ?, ?)`,
      [id, access_token, refresh_token || null]
    );

    // ロール付与（任意）
    await axios.put(
      `https://discord.com/api/guilds/${guildId}/members/${id}/roles/${roleId}`,
      {},
      { headers: { Authorization: `Bot ${BOT_TOKEN}` } }
    ).catch(() => {}); // エラー無視でもOK

    // 成功ページ
    const html = SUCCESS_HTML.replace('{{username}}', username || 'ユーザー');
    res.send(html);
  } catch (error) {
    console.error(error);
    res.status(400).send('認証に失敗しました');
  }
});

// Discord.js イベント・コマンド
client.once('ready', async () => {
  console.log(`Logged in as ${client.user.tag}`);

  // スラッシュコマンド登録
  const commands = [
    {
      name: 'button',
      description: '認証ボタンを設置します',
      options: [
        {
          name: 'role',
          description: '付与するロール',
          type: 8, // Role
          required: true,
        },
      ],
    },
    {
      name: 'call',
      description: '保存済みメンバーを一括でサーバーに追加します',
    },
    {
      name: 'backupdata',
      description: '現在のバックアップ人数を表示します',
    },
  ];

  const rest = new REST({ version: '10' }).setToken(BOT_TOKEN);

  try {
    await rest.put(Routes.applicationCommands(client.user.id), { body: commands });
    console.log('Successfully registered application commands.');
  } catch (error) {
    console.error(error);
  }
});

// コマンド処理
client.on('interactionCreate', async (interaction) => {
  if (!interaction.isChatInputCommand()) return;

  const { commandName } = interaction;

  // 管理者権限チェック
  if (!interaction.member.permissions.has(PermissionsBitField.Flags.Administrator)) {
    return interaction.reply({ content: 'このコマンドは管理者のみ使用可能です。', ephemeral: true });
  }

  if (commandName === 'button') {
    const role = interaction.options.getRole('role');

    const state = `${interaction.guild.id}:${role.id}`;
    const params = new URLSearchParams({
      client_id: CLIENT_ID,
      redirect_uri: REDIRECT_URI,
      response_type: 'code',
      scope: 'identify guilds.join',
      state,
    });

    const url = `https://discord.com/api/oauth2/authorize?${params}`;

    const embed = new EmbedBuilder()
      .setTitle('認証')
      .setDescription('下の認証ボタンを押して認証を完了してください！')
      .setColor(0xffc0cb);

    const row = new ActionRowBuilder().addComponents(
      new ButtonBuilder().setLabel('認証').setStyle(ButtonStyle.Link).setURL(url)
    );

    await interaction.channel.send({ embeds: [embed], components: [row] });

    await interaction.reply({ content: 'バックアップパネルを設置しました！', ephemeral: true });
  }

  else if (commandName === 'call') {
    const userId = interaction.user.id;
    const now = Math.floor(Date.now() / 1000);

    db.get('SELECT last_call FROM call_limit WHERE user_id = ?', [userId], async (err, row) => {
      if (err) return interaction.reply({ content: 'エラーが発生しました', ephemeral: true });

      if (row && now - row.last_call < 3600) {
        const remain = 3600 - (now - row.last_call);
        const m = Math.floor(remain / 60);
        const s = remain % 60;
        return interaction.reply({ content: `再使用まで ${m}分${s}秒`, ephemeral: true });
      }

      await interaction.deferReply({ ephemeral: true });

      db.all('SELECT id, access_token FROM users', async (err, users) => {
        if (err) return interaction.editReply({ content: 'データベースエラー' });

        let added = 0, already = 0, failed = 0;

        for (const { id, access_token } of users) {
          const status = await addGuildMember(interaction.guild.id, id, access_token);
          if (status === 201) added++;
          else if (status === 204) already++;
          else failed++;
        }

        // 使用時間記録
        db.run('INSERT OR REPLACE INTO call_limit (user_id, last_call) VALUES (?, ?)', [userId, now]);

        const embed = new EmbedBuilder()
          .setTitle('メンバー追加結果')
          .setColor(0x00ff7f)
          .addFields(
            { name: '追加人数', value: `${added}人`, inline: true },
            { name: '参加済み', value: `${already}人`, inline: true },
            { name: '失敗人数', value: `${failed}人`, inline: true }
          );

        await interaction.editReply({ embeds: [embed] });
      });
    });
  }

  else if (commandName === 'backupdata') {
    await interaction.deferReply({ ephemeral: true });

    db.get('SELECT COUNT(*) as count FROM users', (err, row) => {
      if (err) return interaction.editReply({ content: 'エラー' });

      const embed = new EmbedBuilder()
        .setTitle('バックアップ状況')
        .setColor(0x87ceeb)
        .addFields({ name: 'ユーザー数', value: `${row.count}人` });

      interaction.editReply({ embeds: [embed] });
    });
  }
});

// 24時間ごとにトークン更新
cron.schedule('0 0 * * *', refreshAllTokens);

// サーバー起動
app.listen(PORT, () => {
  console.log(`OAuth callback server running on port ${PORT}`);
});

// Discordログイン
client.login(BOT_TOKEN).catch(console.error);


// npm install axios discord.js dotenv express node-cron sqlite3 @discordjs/rest @discordjs/builders


// .env
//CLIENT_ID=xxx
//CLIENT_SECRET=xxx
//REDIRECT_URI=https://your-domain.com/backup_member
//Token=Bot xxxxxxxxxxxxxxxxxxxxxxxxxxx
