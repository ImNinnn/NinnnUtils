# NinnnUtils
Discord bot for small servers

This bot has been made using the discord.py library !
the bot is versatile and is usable anywhere ;)
this bot adds:
- basic fun and useful utility commands
- commands for server admins
- An economy and Leveling system
- Minigames (Economy minigames, Counter)
- Welcome and goodbye messages with banners

## Links

Install Link https://discord.com/oauth2/authorize?client_id=1500798502735708281

**Support Server https://discord.gg/FSBPvc9zqY**

ToS and Privacy policy https://imninnn.github.io

## Usage
###  Installation

Run these commands to install the deps in a few seconds

```shell
git clone https://github.com/ImNinnn/NinnnUtils
cd NinnnUtils
pip install -r requirements.txt
```

### Configuration
Oooopen .env up for editing, we'll configure the bot here

#### Fields

| Argument              | Description                                                                                                       | Example                         |
|-----------------------|-------------------------------------------------------------------------------------------------------------------|---------------------------------|
| DISCORD_TOKEN         | Bot token (bot only, you can't run selfbots)                                                                      | MTUwMDc5ODUwMjczNTcwODI4MQ==... |
| BOT_VERSION           | The version the bot will show in RPC and infos (semantic versioning recommended)                                  | v4.5.0                          |
| ACTIVITY              | The activity that displays on the bot's profile (playing/watching)                                                | [none, idk what is the example] |
| SERVER_BLACKLIST      | This will make the bot leave any servers you don't want it in                                                     | [this too]                      |
| SHARD_COUNT           | Sharding is required when your bot reaches 1500 servers or more, this specifies how many shards the bot will have | 10                              |
| DISCORD_RPC_CLIENT_ID | The app ID that will be used for __your__ RPC                                                                     | 1500798502735708281             |
| PREFIX                | Prefix for owner commands (Will also be for normal commands, trust me ;)                                          | n!                              |
| OWN_PASSWORD          | Passwords for owner commands                                                                                      | 1mC00k3d!!1                     |
