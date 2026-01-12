// index.js
require('dotenv').config();
const { Client, GatewayIntentBits, Partials } = require('discord.js');

// 環境変数からトークンを取得
const BOT_TOKEN = process.env.Token;

if (!BOT_TOKEN) {
  console.error('Error: BOT_TOKEN が .env ファイルに設定されていません');
  process.exit(1);
}

// Discordクライアントの作成
const client = new Client({
  intents: [
    GatewayIntentBits.Guilds,
    GatewayIntentBits.GuildMembers,
    GatewayIntentBits.GuildMessages,
    GatewayIntentBits.MessageContent, // メッセージ内容を取得するために必要
  ],
  partials: [
    Partials.Message,
    Partials.Channel,
    Partials.User,
  ],
});

// コマンド登録・Cog相当の処理をここにまとめる想定
// (元のコードでは from backup import setup を使っていた部分)
async function loadFeatures() {
  // ここにスラッシュコマンドやイベントリスナーの登録を行う
  // 実際の機能は別ファイル（例: features/backup.js など）に分けるのがおすすめ

  console.log('Loading features...');

  // 例: バックアップ機能の読み込み（仮）
  // const backup = require('./features/backup');
  // await backup.setup(client);

  // 実際には以下のような感じで実装されることが多いです
  // client.commands = new Collection();
  // 各コマンドファイルを読み込んで登録...
}

// readyイベント
client.once('ready', async () => {
  console.log(`Logged in as ${client.user.tag}`);
  console.log(`サーバー数: ${client.guilds.cache.size}`);
  console.log(`ユーザー数: ${client.users.cache.size}`);

  // 機能の読み込み
  await loadFeatures();

  // スラッシュコマンドの同期（グローバル）
  // ※開発中は guildId を指定して同期する方が早い
  try {
    await client.application.commands.set([]); // 必要に応じて既存コマンド削除
    console.log('スラッシュコマンドの同期が完了しました');
  } catch (error) {
    console.error('スラッシュコマンド同期エラー:', error);
  }
});

// エラーハンドリング（推奨）
client.on('error', (error) => {
  console.error('Client error:', error);
});

client.on('shardError', (error) => {
  console.error('Shard error:', error);
});

// メイン処理
async function main() {
  try {
    await client.login(BOT_TOKEN);
  } catch (error) {
    console.error('ログインに失敗しました:', error);
    process.exit(1);
  }
}

// 実行
main().catch(console.error);

// Ctrl+C で安全に終了
process.on('SIGINT', () => {
  console.log('\nボットを終了しています...');
  client.destroy();
  process.exit(0);
});
