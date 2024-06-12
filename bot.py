import discord
from discord.ext import commands
from discord.ui import Button, View
import requests
from bs4 import BeautifulSoup
import random
import asyncio

intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

# Словари для хранения данных
player_cards = {}
current_matches = {}
match_channels = {}
command_channels = {}
challenge_messages = {}
rps_inventory = {"rock": 0, "scissors": 0, "paper": 0}
table_message = None
player_resources = {}  # Словарь для хранения количества ресурсов у игроков

# Название роли, для которой нужно отслеживать ресурсы
tracked_role_name = "TrackedRole"

# Установим начальное количество ресурсов для всех участников
default_resources = {"rock": 3, "scissors": 3, "paper": 3}

class ChallengeView(View):
    def __init__(self, challenger, challengee, ctx):
        super().__init__(timeout=60)
        self.challenger = challenger
        self.challengee = challengee
        self.ctx = ctx

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.green)
    async def accept_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.challengee:
            await interaction.response.send_message("You are not the challengee.", ephemeral=True)
            return

        guild = interaction.guild

        # Create a channel for the challenger if not exists
        challenger_channel = None
        if self.challenger.id not in match_channels:
            challenger_overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                self.challenger: discord.PermissionOverwrite(read_messages=True, send_messages=True),
                guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
            }
            challenger_channel = await guild.create_text_channel(
                f'challenger-{self.challenger.display_name}',
                overwrites=challenger_overwrites
            )
            match_channels[self.challenger.id] = challenger_channel.id
        else:
            challenger_channel = bot.get_channel(match_channels[self.challenger.id])

        # Create a channel for the challengee if not exists
        challengee_channel = None
        if self.challengee.id not in match_channels:
            challengee_overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                self.challengee: discord.PermissionOverwrite(read_messages=True, send_messages=True),
                guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
            }
            challengee_channel = await guild.create_text_channel(
                f'challengee-{self.challengee.display_name}',
                overwrites=challengee_overwrites
            )
            match_channels[self.challengee.id] = challengee_channel.id
        else:
            challengee_channel = bot.get_channel(match_channels[self.challengee.id])

        current_matches[self.challenger.id] = self.challengee.id
        current_matches[self.challengee.id] = self.challenger.id

        command_channels[self.challenger.id] = self.ctx.channel.id
        command_channels[self.challengee.id] = self.ctx.channel.id

        await interaction.response.send_message(
            f'{self.challenger.mention} и {self.challengee.mention}, вызов на матч был принят. Присылайте свои карты в созданные для вас каналы, они должны быть в самом верху сервера.',
            ephemeral=False
        )

        # Delete the challenge command and response messages
        challenge_command_message, challenge_response_message = challenge_messages[self.challenger.id]
        await challenge_command_message.delete()
        await challenge_response_message.delete()

        self.stop()

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.red)
    async def decline_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.challengee:
            await interaction.response.send_message("You are not the challengee.", ephemeral=True)
            return

        await interaction.response.send_message(f'{self.challengee.mention} declined the challenge.', ephemeral=False)
        self.stop()

class RPSView(View):
    def __init__(self, challenger, challengee):
        super().__init__(timeout=60)
        self.challenger = challenger
        self.challengee = challengee
        self.challenger_choice = None
        self.challengee_choice = None
        self.message = None

    @discord.ui.button(label="Rock", style=discord.ButtonStyle.gray)
    async def rock_button(self, interaction: discord.Interaction, button: Button):
        await self.process_choice(interaction, "rock")

    @discord.ui.button(label="Scissors", style=discord.ButtonStyle.gray)
    async def scissors_button(self, interaction: discord.Interaction, button: Button):
        await self.process_choice(interaction, "scissors")

    @discord.ui.button(label="Paper", style=discord.ButtonStyle.gray)
    async def paper_button(self, interaction: discord.Interaction, button: Button):
        await self.process_choice(interaction, "paper")

    @discord.ui.button(label="Leave", style=discord.ButtonStyle.red)
    async def leave_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.challenger and interaction.user != self.challengee:
            await interaction.response.send_message("You are not part of this game.", ephemeral=True)
            return

        await interaction.response.send_message(f"{interaction.user.display_name} left the game.", ephemeral=True)
        await self.message.delete()
        self.stop()

    async def process_choice(self, interaction: discord.Interaction, choice: str):
        if interaction.user == self.challenger:
            self.challenger_choice = choice
        elif interaction.user == self.challengee:
            self.challengee_choice = choice
        else:
            await interaction.response.send_message("You are not part of this game.", ephemeral=True)
            return

        await interaction.response.send_message(f"{interaction.user.display_name} chose {choice}.", ephemeral=True)
        
        if self.challenger_choice and self.challengee_choice:
            await self.show_result()

    async def show_result(self):
        # Удаляем сообщение с кнопками
        for child in self.children:
            child.disabled = True
        await self.message.edit(view=self)

        await asyncio.sleep(3)  # Подождите 3 секунды перед отображением результата

        # Определяем результат
        result = None
        if self.challenger_choice == self.challengee_choice:
            result = "It's a tie!"
        elif (self.challenger_choice == "rock" and self.challengee_choice == "scissors") or \
             (self.challenger_choice == "scissors" and self.challengee_choice == "paper") or \
             (self.challenger_choice == "paper" and self.challengee_choice == "rock"):
            result = f"{self.challenger.display_name} wins!"
        else:
            result = f"{self.challengee.display_name} wins!"

        images = {
            "rock": r"C:\Users\Роман\Desktop\Jababot\rock.png",
            "scissors": r"C:\Users\Роман\Desktop\Jababot\scissors.png",
            "paper": r"C:\Users\Роман\Desktop\Jababot\paper.png"
        }

        challenger_image = discord.File(images[self.challenger_choice], filename=f"{self.challenger_choice}.png")
        challengee_image = discord.File(images[self.challengee_choice], filename=f"{self.challengee_choice}.png")

        embed = discord.Embed(title="Rock Paper Scissors Result")
        embed.add_field(name=f"{self.challenger.display_name}'s choice", value=self.challenger_choice.capitalize())
        embed.add_field(name=f"{self.challengee.display_name}'s choice", value=self.challengee_choice.capitalize())
        embed.add_field(name="Result", value=result)
        embed.set_image(url=f"attachment://{self.challenger_choice}.png")

        await self.message.channel.send(file=challenger_image, embed=embed)
        await self.message.channel.send(file=challengee_image)

        # Обновление ресурсов игроков и таблицы
        await decrease_player_resource(self.challenger.id, self.challenger_choice)
        await decrease_player_resource(self.challengee.id, self.challengee_choice)

async def update_table(channel):
    global table_message
    content = f"**Rock Paper Scissors Inventory**\nRock: {rps_inventory['rock']}\nScissors: {rps_inventory['scissors']}\nPaper: {rps_inventory['paper']}"
    if table_message:
        await table_message.edit(content=content)
    else:
        table_message = await channel.send(content)

async def decrease_player_resource(player_id, resource):
    if player_id not in player_resources:
        player_resources[player_id] = default_resources.copy()
    
    player_resources[player_id][resource] -= 1

    # Обновляем глобальную таблицу ресурсов
    rps_inventory[resource] -= 1

    # Отправляем сообщение в консоль о изменении ресурса
    player = bot.get_user(player_id)
    print(f"Updated {player.display_name}'s resources: {resource} = {player_resources[player_id][resource]}")

    # Обновляем таблицу в чате
    if table_message:
        await update_table(table_message.channel)

@bot.command(name='init')
@commands.has_permissions(administrator=True)
async def initialize_table(ctx):
    global table_message
    table_message = await ctx.send(f"**Rock Paper Scissors Inventory**\nRock: {rps_inventory['rock']}\nScissors: {rps_inventory['scissors']}\nPaper: {rps_inventory['paper']}")

@bot.command(name='add')
@commands.has_permissions(administrator=True)
async def add_items(ctx, item: str, count: int):
    if item in rps_inventory:
        rps_inventory[item] += count
        await ctx.send(f"Added {count} {item}(s) to the inventory.")
        await update_table(ctx.channel)
    else:
        await ctx.send("Invalid item. Please use 'rock', 'scissors', or 'paper'.")

@bot.command(name='rps')
async def rock_paper_scissors(ctx, member: discord.Member):
    if rps_inventory["rock"] == 0 and rps_inventory["scissors"] == 0 and rps_inventory["paper"] == 0:
        await ctx.send("There are no items available to play. Please ask an admin to add some.")
        return

    if member == ctx.author:
        await ctx.send("You cannot play against yourself!")
        return

    if member.bot:
        await ctx.send("You cannot play against a bot!")
        return

    view = RPSView(ctx.author, member)
    view.message = await ctx.send(f"{ctx.author.mention} vs {member.mention}: Choose your move!", view=view)

@bot.command(name='chl')
async def challenge(ctx, member: discord.Member):
    if member == ctx.author:
        await ctx.send("You cannot challenge yourself!")
        return

    if member.bot:
        await ctx.send("You cannot challenge a bot!")
        return

    view = ChallengeView(ctx.author, member, ctx)
    response_message = await ctx.send(f"{member.mention}, вы были вызваны на состязание {ctx.author.mention}!", view=view)

    # Store the challenge command and response messages
    challenge_messages[ctx.author.id] = (ctx.message, response_message)
    challenge_messages[member.id] = (ctx.message, response_message)

@bot.command(name='end')
async def end_game(ctx, member: discord.Member):
    if member.id not in current_matches or ctx.author.id not in current_matches:
        await ctx.send("There is no match found with this player.")
        return

    # Remove match data
    challenger_id = ctx.author.id
    challengee_id = member.id

    del current_matches[challenger_id]
    del current_matches[challengee_id]
    del command_channels[challenger_id]
    del command_channels[challengee_id]
    if challenger_id in player_cards:
        del player_cards[challenger_id]
    if challengee_id in player_cards:
        del player_cards[challengee_id]

    # Delete match channels
    challenger_channel = bot.get_channel(match_channels[challenger_id])
    challengee_channel = bot.get_channel(match_channels[challengee_id])
    await challenger_channel.delete()
    await challengee_channel.delete()

    del match_channels[challenger_id]
    del match_channels[challengee_id]

    await ctx.send(f"Match between {ctx.author.mention} and {member.mention} has been ended.")

@bot.command(name='sch')
async def set_channel(ctx, channel: discord.TextChannel = None):
    if channel is None:
        await ctx.send('You need to specify a channel.')
        return

    bot.target_channel = channel
    await ctx.send(f'Target channel set to {channel.mention}')

@bot.command(name='cmd')
async def show_commands(ctx):
    help_text = """
    **Bot Commands:**
    `!sch <channel>` - Set the target channel.
    `!chl <@member>` - Challenge a member.
    `!end <@member>` - End the match and delete match channels.
    `!init` - Initialize the RPS inventory table. (Admins only)
    `!add <item> <count>` - Add items to the RPS inventory. (Admins only)
    `!rps <@member>` - Play rock-paper-scissors with a member.
    `!bred` - Get a random pasta from /b/.
    `!cmd` - Show this help message.
    `!list <role>` - List all members with a specific role and their resources. (Admins only)
    `!update_resources <@member> <item> <count>` - Update the resources for a specific member. (Admins only)
    """
    await ctx.send(help_text)

@bot.command(name='list')
@commands.has_permissions(administrator=True)
async def list_members_with_role(ctx, role: discord.Role):
    members_with_role = [member for member in ctx.guild.members if role in member.roles]
    if not members_with_role:
        await ctx.send("No members found with this role.")
        return

    response = f"**Members with {role.name} role and their resources:**\n"
    for member in members_with_role:
        if member.id not in player_resources:
            player_resources[member.id] = default_resources.copy()
        resources = player_resources[member.id]
        response += f"{member.display_name}: Rock - {resources['rock']}, Scissors - {resources['scissors']}, Paper - {resources['paper']}\n"

    await ctx.send(response)

@bot.command(name='update_resources')
@commands.has_permissions(administrator=True)
async def update_member_resources(ctx, member: discord.Member, item: str, count: int):
    if item not in default_resources:
        await ctx.send("Invalid item. Please use 'rock', 'scissors', or 'paper'.")
        return

    if member.id not in player_resources:
        player_resources[member.id] = default_resources.copy()

    player_resources[member.id][item] += count
    await ctx.send(f"Updated {member.display_name}'s resources: {item} = {player_resources[member.id][item]}")

@bot.event
async def on_message(message):
    if message.guild is not None and not message.author.bot:
        print(f"Received message in guild from {message.author}: {message.content}")

        # Only process messages from the match channels
        if message.channel.id not in match_channels.values():
            await bot.process_commands(message)
            return

        if message.author.id not in current_matches:
            return

        if not message.attachments:
            await message.channel.send(f'{message.author.mention}, you must send an image!')
            return

        opponent_id = current_matches[message.author.id]
        opponent = message.guild.get_member(opponent_id)
        member = message.guild.get_member(message.author.id)
        display_name = member.display_name

        if message.author.id not in player_cards:
            player_cards[message.author.id] = {'name': display_name, 'cards': []}
        player_cards[message.author.id]['cards'].append(message)

        await message.channel.send(f'{message.author.mention}, card received!')

        # Check if we have two players and at least one card each
        if opponent_id in player_cards and player_cards[opponent_id]['cards']:
            await send_cards(opponent_id, message.author.id)

    await bot.process_commands(message)

async def send_cards(player_1, player_2):
    data_1, data_2 = player_cards[player_1], player_cards[player_2]
    card_1 = data_1['cards'].pop(0)
    card_2 = data_2['cards'].pop(0)

    embed_1 = discord.Embed(title=f"{data_1['name']}'s Card")
    embed_2 = discord.Embed(title=f"{data_2['name']}'s Card")

    if card_1.attachments:
        embed_1.set_image(url=card_1.attachments[0].url)
    if card_2.attachments:
        embed_2.set_image(url=card_2.attachments[0].url)

    # Send both cards to the original command channel
    command_channel_id = command_channels[player_1]
    command_channel = bot.get_channel(command_channel_id)
    await command_channel.send(embed=embed_1)
    await command_channel.send(embed=embed_2)

    # Clear player cards for the next round
    if not data_1['cards'] and not data_2['cards']:
        del player_cards[player_1]
        del player_cards[player_2]

def get_pastas_from_page(page_number):
    url = f"https://2ch.hk/b/{page_number}.html"
    response = requests.get(url)
    soup = BeautifulSoup(response.content, 'html.parser')
    posts = soup.find_all(class_='post__message post__message_op')
    return [post.get_text(separator="\n") for post in posts]

@bot.command(name='bred')
async def random_pasta(ctx):
    all_pastas = []

    for page_number in range(1, 5):
        all_pastas.extend(get_pastas_from_page(page_number))

    if all_pastas:
        random_post = random.choice(all_pastas)
        await ctx.send(random_post)
    else:
        await ctx.send("Couldn't find any posts. Please try again later.")


TOKEN = ''

bot.run(TOKEN)
