#!/usr/bin/env python3

from datetime import date
from datetime import datetime,timedelta
from threading import Timer
import asyncio
import atexit
import base64
import json
import logging
import logging.handlers
import math
import os
import platform
import pprint
import re#eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee
import string
import sys
import time
import traceback
import urllib
import subprocess
import calendar as cal
from random import randrange
from morkpy.postfix import calculate

"""Dependencies"""
import discord
import morkpy.graph as graph
import pyspeedtest
import MySQLdb
import wikipedia, wikia

"""Initialisation"""
from pedant_config import CONF,SQL,MESG
last_message_time = {}
reminders = []
ALLOWED_EMBED_CHARS = ' abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!"#$%&\'()*+,-./:;<=>?@[\]^_`{|}~'

client = discord.Client()

"""Command registration framework"""
import functools,inspect
commands = {}
def register(command_name, *args, **kwargs):
    def w(fn):
        @functools.wraps(fn)
        def f(*args, **kwargs):
            return fn(*args, **kwargs)
        f.command_name = command_name
        f.usage = CONF.get('cmd_pref','/') + command_name + (' ' if args != () else '') + ' '.join(args)
        f.admin = kwargs.get('admin', False)
        f.owner = kwargs.get('owner', False)
        f.rate = kwargs.get('rate',0)
        f.hidden = kwargs.get('hidden',False)
        f.invokes = {}
        f.alias_for = kwargs.get('alias',False)

        commands[command_name] = f
        return f
    return w

"""Setup logging"""
try:
    logging.basicConfig(format=CONF.get('log_format','[%(asctime)s] [%(levelname)s] %(message)s'),stream=sys.stdout)
    logger = logging.getLogger('pedantbot')
    logger.setLevel(logging.INFO)

    log_handler = logging.handlers.RotatingFileHandler(CONF.get('dir_pref','/home/shwam3/')+CONF.get('logfile','{}.log'.format(__file__)), 'a', backupCount=5, delay=True)
    log_handler.setLevel(logging.DEBUG)

    err_log_handler = logging.StreamHandler(stream=sys.stderr)
    err_log_handler.setLevel(logging.WARNING)

    formatter = logging.Formatter(CONF.get('log_format','[%(asctime)s] [%(levelname)s] %(message)s'))
    log_handler.setFormatter(formatter)
    err_log_handler.setFormatter(formatter)


    if os.path.isfile(CONF.get('dir_pref','/home/shwam3/')+CONF.get('logfile','{}.log'.format(__file__))):
        log_handler.doRollover()

    logger.addHandler(log_handler)
    logger.addHandler(err_log_handler)

    logger.warn('Starting...')
except Exception as e:
    print(e)

"""Respond to events"""
@client.event
async def on_ready():
    logger.info('Version ' + CONF.get('VERSION','0.0.0'))
    logger.info('Logged in as:')
    logger.info(' ->    Name: '+ client.user.name)
    logger.info(' ->    ID: '+ client.user.id)

    logger.info('Setting reminders')
    try:
        for rem in reminders:
            if rem.get('is_cancelled', False):
                continue
            task = asyncio.ensure_future(do_reminder(client, rem['invoke_time']))
            rem['task'] = task

        asyncio.ensure_future(update_status())

        logger.info(' -> set ' + str(len(reminders)) + ' reminders')

        save_reminders()
    except:
        pass

"""Respond to messages"""
@client.event
async def on_message(message):
    await client.wait_until_ready()

    try:
        if message.author.id == client.user.id:
            return
        elif message.content.lower().startswith(CONF.get('cmd_pref','/')):
            try:
                inp = message.content.split(' ')
                command_name, command_args = inp[0][1::].lower(),inp[1::]

                cmd = commands[command_name]

                last_used = cmd.invokes.get(message.author.id,False)
                datetime_now = datetime.now()
                if not last_used or (last_used < datetime_now - timedelta(seconds=cmd.rate)):
                    cmd.invokes[message.author.id] = datetime_now

                    try:
                        await client.delete_message(message)
                    except:
                        pass
                    await client.send_typing(message.channel)
                    if not cmd.owner or (cmd.owner and message.author.id in CONF.get('owners',[])):
                        executed = await cmd(message,*command_args)
                        if executed == False:
                            msg = await client.send_message(message.channel,MESG.get('cmd_usage','USAGE: {}.usage').format(cmd))
                            asyncio.ensure_future(message_timeout(msg, 40))
                    else:
                        msg = await client.send_message(message.channel,MESG.get('nopermit','{0.author.mention} Not allowed.').format(message))
                        asyncio.ensure_future(message_timeout(msg, 40))
                else:
                    # Rate-limited
                    pass
            except KeyError:
                msg = await client.send_message(message.channel, MESG.get('cmd_notfound','`{0}` not found.').format(command_name))
                asyncio.ensure_future(message_timeout(msg, 40))

            except Exception as e:
                logger.exception(e)
                msg = await client.send_message(message.channel,MESG.get('error','Error in `{1}`: {0}').format(e,command_name))
                asyncio.ensure_future(message_timeout(msg, 40))
        else:
            await do_record(message)
    except Exception as e:
        logger.error('error in on_message')
        logger.exception(e)
        await log_exception(e, 'on_message')

"""Commands"""
@register('test','[list of parameters]',owner=False,rate=1)
async def test(message,*args):
    """Print debug output"""
    msg = await client.send_message(message.channel,'```py\n{0}\n```\n```py\n{1}\n```'.format(args,message.attachments))

@register('info',rate=5)
async def bot_info(message,*args):
    """Print information about the Application"""
    me = await client.application_info()
    owner = me.owner
    embed = discord.Embed(title=me.name,description=me.description,color=colour(message),timestamp=discord.utils.snowflake_time(me.id))
    embed.set_thumbnail(url=me.icon_url)
    embed.set_author(name=owner.name,icon_url=owner.avatar_url or owner.default_avatar_url)
    embed.set_footer(text="Client ID: {}".format(me.id))

    await client.send_message(message.channel,embed=embed)

@register('help','[command name]',rate=3)
async def help(message,*args):
    """Display help message(s), optionally append command name for specific help"""
    command_name = ' '.join(args)
    if args == ():
        admin_commands = ''; standard_commands = ''
        for command_name,cmd in sorted(commands.items(),key=lambda x: (x[1].owner,x[0])):
            if cmd.alias_for == False and not cmd.hidden:
                if cmd.owner:
                    admin_commands += '{0.usage}'.format(cmd) + "\n"
                else:
                    standard_commands += '{0.usage}'.format(cmd) + "\n"

        embed = discord.Embed(title="Command Help",color=colour(message),description='Prefix: {0}\nUSAGE: {0}command <required> [optional]\nFor more details: {0}help [command] '.format(CONF.get('cmd_pref','/')))
        embed.add_field(name='Standard Commands',value='```'+standard_commands+'```',inline=True)
        embed.add_field(name='Admin Commands',value='```'+admin_commands+'```',inline=True)

        msg = await client.send_message(message.channel,embed=embed)
        asyncio.ensure_future(message_timeout(msg,120))
    else:
        try:
            cmd = commands[command_name]
            embed = discord.Embed(title="__Help for {0.command_name}__".format(cmd),color=colour(message))
            embed.add_field(name="Usage",value='```'+cmd.usage+'```')
            embed.add_field(name="Description",value=cmd.__doc__)
            msg = await client.send_message(message.channel,embed=embed)
            asyncio.ensure_future(message_timeout(msg, 60))
        except KeyError as e:
            logger.exception(e)
            msg = await client.send_message(message.channel,MESG.get('cmd_notfound','`{0}` not found.').format(command_name))
            asyncio.ensure_future(message_timeout(msg, 20))

@register('info',rate=5)
async def bot_info(message,*args):
    """Print information about the Application"""
    me = await client.application_info()
    owner = me.owner
    embed = discord.Embed(title=me.name,description=me.description,color=colour(message),timestamp=discord.utils.snowflake_time(me.id))
    embed.set_thumbnail(url=me.icon_url)
    embed.set_author(name=owner.name,icon_url=owner.avatar_url or owner.default_avatar_url)
    embed.set_footer(text="Client ID: {}".format(me.id))

    await client.send_message(message.channel,embed=embed)

@register('remindme','in <number of> [seconds|minutes|hours]')
async def remindme(message,*args):
    if len(args) < 3:
        return False

    word_units = {'couple':(2,2),'few':(2,4),'some':(3,5), 'many':(5,15), 'lotsa':(10,30)}

    if args[0] != 'in' or (not args[1] in word_units and int(args[1]) <= 0):
        return False

    invoke_time = int(time.time())

    logger.info('Set reminder')
    await client.send_typing(message.channel)

    reminder_msg = ' '.join(args[2::])
    is_cancelled = False
    split = reminder_msg.split(' ',1)
    unit = split[0]
    unit_specified = True
    reminder_if_unit = split[1] if len(split) > 1 else None

    _s = ['seconds','second','sec','secs']
    _m = ['minutes','minute','min','mins']
    _h = ['hours'  ,'hour'  ,'hr' ,'hrs' ]
    _d = ['days'   ,'day'   ,'d'         ]

    if unit in _s:
        unit_mult = 1
    elif unit in _m:
        unit_mult = 60
    elif unit in _h:
        unit_mult = 3600
    elif unit in _d:
        unit_mult = 3600 * 24
    else:
        unit_mult = 60
        unit_specified = False

    if not reminder_if_unit and not unit_specified:
        return False

    if reminder_if_unit and unit_specified:
        reminder_msg = reminder_if_unit

    if not reminder_msg:
        return False

    if args[1] in word_units:
        args[1] = randrange(*word_units[args[1]])

    remind_delta = int(args[1]) * unit_mult
    remind_timestamp = invoke_time + remind_delta

    if remind_delta <= 0:
        msg = await client.send_message(message.channel, MESG.get('reminder_illegal','Illegal argument'))
        asyncio.ensure_future(message_timeout(msg, 20))
        return

    reminder = {'user_name':message.author.display_name, 'user_mention':message.author.mention, 'invoke_time':invoke_time, 'time':remind_timestamp, 'channel_id':message.channel.id, 'message':reminder_msg, 'task':None, 'is_cancelled':is_cancelled}
    reminders.append(reminder)
    async_task = asyncio.ensure_future(do_reminder(client, invoke_time))
    reminder['task'] = async_task

    logger.info(' -> reminder scheduled for ' + str(datetime.fromtimestamp(remind_timestamp)))
    msg = await client.send_message(message.channel, message.author.mention + ' Reminder scheduled for ' + datetime.fromtimestamp(remind_timestamp).strftime(CONF.get('date_format','%A %d %B %Y @ %I:%M%p')))
    asyncio.ensure_future(message_timeout(msg, 60))

    if remind_delta > 15:
        save_reminders()

@register('reminders',rate=1)
async def list_reminders(message,*args):
    logger.info('Listing reminders')

    msg = 'Current reminders:\n'
    reminders_yes = ''; reminders_no = ''

    for rem in reminders:
        try:
            date = datetime.fromtimestamp(rem['time']).strftime(CONF.get('date_format','%A %d %B %Y @ %I:%M%p'))
        except:
            date = str(rem['time'])

        if rem.get('is_cancelled',False):
            reminders_no += ('~~' if rem.get('is_cancelled',False) else '') + rem['user_name'] + ' at ' + date + ': ``' + rem['message'] +'`` (id:`'+str(rem['invoke_time'])+'`)' + ('~~\n' if rem.get('is_cancelled',False) else '\n')
        else:
            reminders_yes += ('~~' if rem.get('is_cancelled',False) else '') + rem['user_name'] + ' at ' + date + ': ``' + rem['message'] +'`` (id:`'+str(rem['invoke_time'])+'`)' + ('~~\n' if rem.get('is_cancelled',False) else '\n')

    if len(reminders) == 0:
        msg += 'No reminders'

    embed = discord.Embed(title="Reminders in {}".format(message.channel.name),color=colour(message))
    if len(reminders_yes) > 0:
        embed.add_field(name='__Current Reminders__',value=reminders_yes)
    if len(reminders_no) > 0:
        embed.add_field(name='__Cancelled Reminders__',value=reminders_no)

    msg = await client.send_message(message.channel, embed=embed)
    asyncio.ensure_future(message_timeout(msg, 90))

@register('cancelreminder','<reminder id>')
async def cancel_reminder(message,*args):
    """Cancel an existing reminder"""
    global reminders
    if len(args) != 1:
        return

    logger.info('Cancel reminder')

    invoke_time = int(args[0])

    try:
        reminder = get_reminder(invoke_time)
        reminder['is_cancelled'] = True
        reminder['task'].cancel()
    except:
        msg = await client.send_message(message.channel,'Reminder not found.')
        asyncio.ensure_future(message_timeout(msg, 20))
        return

    msg = await client.send_message(message.channel,'Reminder #{0[invoke_time]}: `"{0[message]}"` removed.'.format(reminder))
    asyncio.ensure_future(message_timeout(msg, 20))
    reminders = [x for x in reminders if x['invoke_time'] != invoke_time]

@register('editreminder', '<reminder ID> <message|timestamp> [data]',rate=3)
async def edit_reminder(message,*args):
    """Edit scheduled reminders"""
    logger.info('Edit reminder')

    invoke_time = int(args[0])

    reminder = get_reminder(invoke_time)

    if not reminder:
        msg = await client.send_message(message.channel, 'Invalid reminder ID `{0}`'.format(invoke_time))
        asyncio.ensure_future(message_timeout(msg, 20))
        return

    try:
        if args[1].lower() in ['message','msg']:
            reminder['message'] = ' '.join(args[2::])

        elif args[1].lower() in ['timestamp','time','ts']:
            reminder['time'] = int(args[2])

        else:
            return False
    except:
        return False

    reminder['task'].cancel()
    async_task = asyncio.ensure_future(do_reminder(client, invoke_time))
    reminder['task'] = async_task

    msg = await client.send_message(message.channel, 'Reminder re-scheduled')
    asyncio.ensure_future(message_timeout(msg, 40))

@register('ping','[<host> [count]]',rate=5)
async def ping(message,*args):
    """Test latency by receiving a ping message"""
    await client.send_message(message.channel, MESG.get('ping','Pong.'))

@register('ip', owner=True)
async def ip(message,*args,owner=True):
    """Looks up external IP of the host machine"""
    response = urllib.request.urlopen('https://api.ipify.org/')
    IP_address = response.read().decode('utf-8')

    output = subprocess.run("ip route | awk 'NR==2 {print $NF}'", shell=True, stdout=subprocess.PIPE, universal_newlines=True)

    embed = discord.Embed(title="IP address for {user.name}".format(user=client.user),color=colour(message))
    try:
        embed.add_field(name='Internal',value='```'+output.stdout+'```')
    except Exception as e:
        logger.exception(e)
    embed.add_field(name='External',value='```'+IP_address+'```')

    await client.send_message(message.channel, embed=embed)

@register('speedtest',owner=True,rate=5)
async def speedtest(message):
    """Run a speedtest from the bot's LAN."""
    st = pyspeedtest.SpeedTest(host='speedtest.as50056.net')
    msg = await client.send_message(message.channel, MESG.get('st_start','Speedtest ...'))

    try:
        ping = str(round(st.ping(),1))
        logger.info(' -> ping: ' + ping + 'ms')
        msg = await client.edit_message(msg, MESG.get('st_ping','Speedtest:\nping: {0}ms ...').format(ping))

        down = str(round(st.download()/1024/1024,2))
        logger.info(' -> download: ' + down + 'Mb/s')
        msg = await client.edit_message(msg, MESG.get('st_down','Speedtest:\nping: {0}ms,  up: {1}MB/s ...').format(ping,down))

        up = str(round(st.upload()/1024/1024,2))
        logger.info(' -> upload: ' + up + 'Mb/s')
        msg = await client.edit_message(msg, MESG.get('st_up','Speedtest:\nping: {0}ms,  up: {1}MB/s, down: {2}MB/s').format(ping,down,up))

    except Exception as e:
        logger.exception(e)
        msg = await client.edit_message(msg, msg.content + MESG.get('st_error','Error.'))
        asyncio.ensure_future(message_timeout(msg, 20))

@register('oauth','[OAuth client ID] [server ID]')
async def oauth_link(message,*args):
    """Get OAuth invite link"""
    logger.info('OAuth')
    if len(args) > 3:
        return False

    client_id = args[0] if len(args) > 0 else None
    server_id = args[1] if len(args) > 1 else None

    msg = await client.send_message(message.channel, discord.utils.oauth_url(client_id if client_id else client.user.id,
        permissions=discord.Permissions(permissions=1848765527),
        redirect_uri=None))
    asyncio.ensure_future(message_timeout(msg, 120))

@register('invites')
async def get_invite(message,*args):
    """List active invite link for the current server"""
    active_invites = await client.invites_from(message.server)

    revoked_invites   = ['~~{0.url}: `{0.channel}` created by `{0.inviter}`~~ '.format(x) for x in active_invites if x.revoked]
    unlimited_invites = [  '{0.url}: `{0.channel}` created by `{0.inviter}`'.format(x) for x in active_invites if x.max_age == 0 and x not in revoked_invites]
    limited_invites   = [  '{0.url}: `{0.channel}` created by `{0.inviter}`'.format(x) for x in active_invites if x.max_age != 0 and x not in revoked_invites]

    embed = discord.Embed(title='__Invite links for {0.name}__'.format(message.server),
        color=colour(message))
    if unlimited_invites:
        embed.add_field(name='Unlimited Invites',value='\n'.join(unlimited_invites))
    if limited_invites:
        embed.add_field(name='Temporary/Finite Invites', value='\n'.join(limited_invites))
    if revoked_invites:
        embed.add_field(name='Revoked Invites', value='\n'.join(revoked_invites))

    msg = await client.send_message(message.channel,embed=embed)
    asyncio.ensure_future(message_timeout(msg, 120))

@register('watta','<term>',rate=5,alias='define')
@register('pedant','<term>',rate=5,alias='define')
@register('define','<term>',rate=5)
async def define(message, *args):
    """Search for a wikipedia page and show summary"""
    if not args:
        return False

    term = ' '.join(args)
    search = term
    content = None
    found = False

    logger.info('Finding definition: "' + term + '"')

    if term == 'baer':
        await client.send_message(message.channel,'Definition for `baer`:\n```More bae than aforementioned article```')
        return

    if term in special_defs:
        logger.info(' -> Special def')
        content = special_defs[term.lower()]
        if content.startswith('wiki:'):
            term = content[5:]
            content = None
        else:
            found = True

    try:
        if not found:
            arts = wikipedia.search(term)
            if len(arts) == 0:
                logger.info(' -> No results found')
                msg = await client.send_message(message.channel, MESG.get('define_none','`{0}` not found.').format(term))
                asyncio.ensure_future(message_timeout(msg, 40))
                return
            else:
                logger.info(' -> Wiki page')
                try:
                    content = wikipedia.summary(arts[0], chars=750)
                except wikipedia.DisambiguationError as de:
                    logger.info(' -> ambiguous wiki page')
                    content = wikipedia.summary(de.options[0], chars=750)

        logger.info(' -> Found stuff')
        embed = discord.Embed(title=MESG.get('define_title','{0}').format(term),
                              description=''.join([x for x in content if x in ALLOWED_EMBED_CHARS]),
                              color=colour(message)
                             )

        await client.send_message(message.channel,embed=embed)
    except Exception as e:
        logger.exception(e)
        msg = await client.send_message(message.channel,MESG.get('define_error','Error searching for {0}').format(term))
        asyncio.ensure_future(message_timeout(msg, 40))

@register('random',rate=5)
async def random_wiki(message,*args):
    """Retrieve a random WikiPedia article"""
    logger.info('Finding random article')
    term = wikipedia.random(pages=1)

    logger.info(' -> Found: ' + term)
    embed = discord.Embed(title='Random article',
                            type='rich',
                            url='https://en.wikipedia.org/wiki/'+term,
                            description=''.join(x for x in wikipedia.summary(term, chars=450) if x in ALLOWED_EMBED_CHARS),
                            color=colour(message)
                         )
    embed.set_thumbnail(url='https://en.wikipedia.org/static/images/project-logos/enwiki.png')
    embed.set_author(name=term)
    embed.set_footer(text='Requested: random')

    await client.send_message(message.channel, embed=embed)

@register('shrug')
async def shrug(message,*args):
    """Send a shrug: mobile polyfill"""
    embed = discord.Embed(title=message.author.name+' sent something:',description='¯\_(ツ)_/¯',color=colour(message),timestamp=datetime.now())
    await client.send_message(message.channel,embed=embed)

@register('wrong')
async def wrong(message,*args):
    """Send the WRONG! image"""
    embed = discord.Embed(title='THIS IS WRONG!',color=colour(message))
    embed.set_image(url='http://i.imgur.com/CMBlDO2.png')

    await client.send_message(message.channel,embed=embed)

@register('thyme')
async def thyme(message,*args):
    """Send some thyme to your friends"""
    embed = discord.Embed(title='Thyme',timestamp=message.edited_timestamp or message.timestamp,color=colour(message))
    embed.set_image(url='http://shwam3.altervista.org/thyme/image.jpg')
    embed.set_footer(text='{} loves you long thyme'.format(message.author.name))

    await client.send_message(message.channel,embed=embed)

@register('grid','<width> <height>',rate=1)
async def emoji_grid(message,*args):
    """Display a custom-size grid made of server custom emoji"""
    try:
        x = int(args[0]); y = int(args[1])
    except ValueError:
        x,y = 0,0

    x,y = min(x,12),min(y,4)

    emoji = message.server.emojis
    string = '**{}x{} Grid of {} emoji:**\n'.format(x,y,len(emoji))

    for i in range(y):
        for j in range(x):
            temp = emoji[randrange(len(emoji))]
            temp_emoji = '<:{}:{}> '.format(temp.name,temp.id)
            if len(string) + len(temp_emoji) <= 2000:
                string += temp_emoji
        if i < y-1:
            string += '\n'

    await client.send_message(message.channel,string)

@register('showemoji')
async def showemoji(message,*args):
    """Displays all available custom emoji in this server"""
    await client.send_message(message.channel,' '.join(['{}'.format('<:{}:{}>'.format(emoji.name,emoji.id),emoji.name) for emoji in message.server.emojis]))

@register('bigger','<custom server emoji>')
async def bigger(message,*args):
    """Display a larger image of the specified emoji"""
    logger.info('Debug emoji:')
    await client.send_typing(message.channel)

    try:
        thisEmoji = args[0]
    except:
        return False

    if thisEmoji:
        logger.info(' -> ' + thisEmoji)

    useEmoji = None
    for emoji in message.server.emojis:
        if str(emoji).lower() == thisEmoji.lower():
            useEmoji = emoji

    emoji = useEmoji
    if useEmoji != None:
        logger.info(' -> id: ' + emoji.id)
        logger.info(' -> url: ' + emoji.url)

        embed = discord.Embed(title=emoji.name,color=colour(message))
        embed.set_image(url=emoji.url)
        embed.set_footer(text='ID #'+emoji.id)

        await client.send_message(message.channel,embed=embed)
    else:
        msg = await client.send_message(message.channel,MESG.get('emoji_unsupported','Unsupported emoji.').format(message.server.name))
        asyncio.ensure_future(message_timeout(msg, 40))

@register('avatar','@<mention user>',rate=1)
async def avatar(message,*args):
    """Display a user's avatar"""
    if len(message.mentions) < 1:
        return False

    user = message.mentions[0]
    name = user.nick or user.name
    avatar = user.avatar_url or user.default_avatar_url

    embed = discord.Embed(title=name,type='rich',colour=colour(message))
    embed.set_image(url=avatar)
    embed.set_footer(text='ID: #{}'.format(user.id))
    await client.send_message(message.channel,embed=embed)

@register('elijah')
async def alijah(message,*args):
    """elijah wood"""
    await client.send_message(message.channel,'https://i.imgur.com/LNtElui.gifv')

@register('woop')
async def whooup(message, *args):
    """fingers or something"""
    await client.send_message(message.channel, 'http://pa1.narvii.com/5668/5027f4002c6394d487e8d20e0514b0b464afa185_hq.gif')

@register('vote','"<vote question>" <sequence of emoji responses>',rate=30)
async def vote(message,*args):
    """Initiate a vote using Discord Message Reactions."""
    logger.info(message.author.name + ' started a vote')

    await client.send_typing(message.channel)
    stuff = ' '.join(args)

    try:
        q, question = re.findall('(["\'])([^\\1]*)\\1',stuff)[0]
    except:
        return False

    allowedReactions = str(stuff[len(q+question+q)+1:]).replace('  ',' ').split()

    if len(allowedReactions) < 1:
        return False

    logger.info(' -> "' + question + '"')
    logger.info(' -> %s' % ', '.join(allowedReactions))

    msg = await client.send_message(message.channel, MESG.get('vote_title','"{0}" : {1}').format(question,allowedReactions))
    digits = MESG.get('digits',['0','1','2','3','4','5','6','7','8','9'])

    for e in allowedReactions:
        await client.add_reaction(msg, e)
    for i in range(30,0,-1):
        tens = round((i - (i % 10)) / 10)
        ones = i % 10
        num = (digits[tens] if (tens > 0) else '') + ' ' + digits[ones]

        await client.edit_message(msg,msg.content + MESG.get('vote_timer','Time left: {0}').format(num))
        await asyncio.sleep(1)

    await client.edit_message(msg,msg.content + MESG.get('vote_ended','Ended.'))
    msg = await client.get_message(msg.channel,msg.id)

    reacts = []
    validReactions = 0

    if len(msg.reactions) == 0:
        await client.send_message(msg.channel,MESG.get('vote_none','No valid votes.'))
        logger.info(' -> no winner')

    else:
        for reaction in msg.reactions:
            if reaction.emoji in allowedReactions:
                if reaction.count > 1:
                    reacts.append((reaction.emoji,reaction.count -1))
                    validReactions += 1

        if validReactions == 0:
            await client.send_message(msg.channel,MESG.get('vote_none','No valid votes.'))
            logger.info(' -> no winner')

        else:
            reacts = sorted(reacts, key=lambda x: x[1])
            reacts.reverse()

            await client.send_message(msg.channel,MESG.get('vote_win','"{0}", Winner: {1}').format(question,reacts[0][0],graph=graph.draw(msg.reactions,height=5,find=lambda x: x.count-1)))
            logger.info(' -> %s won' % reacts[0][0])

@register('quote','[quote id]',rate=2)
async def quote(message,*args):
    """Embed a quote from https://themork.co.uk/quotes"""
    logger.info('Quote')

    try:
        id = args[0]
    except:
        id = ''

    users = {'kush':'94897568776982528',
             'david b':'240904516269113344',
             'beard matt':'143529460744978432',
             'dawid':'184736498824773634',
             'jaime':'233244375285628928',
             'oliver barnwell':'188672208233693184',
             'orane':'',
             'william':'191332830519885824',
             'shwam3':'154543065594462208',
             'themork':'154542529591771136',
             'wensleydale':'154565902828830720',
             'minkle':'130527313673584640',
             }

    cnx = MySQLdb.connect(user='readonly', db='my_themork')
    cursor = cnx.cursor()

    query = ("SELECT * FROM `q2` WHERE `id`='{}' ORDER BY RAND() LIMIT 1".format(id))
    cursor.execute(query)

    if cursor.rowcount < 1:
        query = ("SELECT * FROM `q2` ORDER BY RAND() LIMIT 1")
        cursor.execute(query)

    for (id,quote,author,date,_,_) in cursor:
        if author.lower() in users:
            try:
                user = message.server.get_member(users[author.lower()])
                name = user.name
            except:
                user = await client.get_user_info(users[author.lower()])

        embed = discord.Embed(title='TheMork Quotes',
                                description=quote,
                                type='rich',
                                url='https://themork.co.uk/quotes/?q='+ str(id),
                                timestamp=datetime(*date.timetuple()[:-4]),
                                color=colour(message)
        )
        embed.set_thumbnail(url='https://themork.co.uk/assets/main.png')
        try:
            embed.set_author(name=user.display_name or user.name,icon_url=user.avatar_url or user.default_avatar_url)
        except:
            embed.set_author(name=author)
        embed.set_footer(text='Quote ID: #' + str(id))

        await client.send_message(message.channel,embed=embed)
        break

    cursor.close()
    cnx.close()

@register('cal')
async def calendar(message,*args):
    """Displays a formatted calendar"""
    today = datetime.now()
    embed = discord.Embed(title='Calender for {0.month}/{0.year}'.format(today),
        description='```\n{0}\n```'.format(cal.month(today.year,today.month)),
        color=colour(message))
    msg = await client.send_message(message.channel,embed=embed)
    asyncio.ensure_future(message_timeout(msg, 120))

@register('servers',owner=True)
async def connected_servers(message,*args):
    """Lists servers currently connected"""
    servers = ['•   **{server.name}** (`{server.id}`)'.format(server=x) for x in client.servers]

    embed = discord.Embed(title='Servers {0} is connected to.'.format(client.user),
        colour=colour(message),
            description='\n'.join(servers))
    msg = await client.send_message(message.channel,embed=embed)
    asyncio.ensure_future(message_timeout(msg, 120))

@register('channels','[server ID]',owner=True)
async def connected_channels(message,*args):
    """Displays a list of channels and servers currently available"""
    embed = discord.Embed(title='Channels {user.name} is conected to.'.format(user=client.user), colour=colour(message))
    for server in client.servers:
        embed.add_field(name='**{server.name}** (`{server.id}`)'.format(server=server), value='\n'.join(['•   **{channel.name}** (`{channel.id}`)'.format(channel=x) for x in server.channels if x.type == discord.ChannelType.text]))
    msg = await client.send_message(message.channel, embed=embed)
    asyncio.ensure_future(message_timeout(msg, 180))

@register('ranks',owner=True)
async def server_ranks(message,*args):
    """Displays a list of ranks in the server"""
    embed = discord.Embed(title='Ranks for {server.name}.'.format(server=message.server), colour=colour(message))
    for role in message.server.roles:
        if not role.is_everyone:
            members = ['•   **{user.name}** (`{user.id}`)'.format(user=x) for x in message.server.members if role in x.roles]
            if len(members) > 0:
                embed.add_field(name='__{role.name}__ ({role.colour} `{role.id}`)'.format(role=role), value='\n'.join(members), inline=False)
    msg = await client.send_message(message.channel, embed=embed)
    asyncio.ensure_future(message_timeout(msg, 180))

@register('age',rate=10)
async def age(message,*args):
    """Get user's Discord age"""
    users = []
    if len(args) < 1:
        users = message.server.members
    else:
        for arg in args:
            users.append(await client.get_user_info(arg))

    for mention in message.mentions:
        users.append(mention)

    string = ''
    for user in users:
        string += '•  **{user}**:`{user.id}` joined on `{date}`\n'.format(user=user,date=discord.utils.snowflake_time(user.id).strftime('%d %B %Y @ %I:%M%p'))

    embed = discord.Embed(title="Age of users in {server.name}".format(server=message.server),
        color=colour(message),
        description=string)

    msg = await client.send_message(message.channel,embed=embed)
    asyncio.ensure_future(message_timeout(msg, 180))

@register('abuse','<channel> <content>',owner=True,alias='sendmsg')
@register('sendmsg','<channel> <content>',owner=True)
async def abuse(message,*args):
    """Harness the power of Discord"""
    if len(args) < 2:
        return False

    channel = args[0]
    if channel == 'here':
        channel = message.channel.id
    msg = ' '.join(args[1::])

    try:
        if channel == 'all':
            for chan in client.get_all_channels():
                await client.send_message(client.get_channel(chan),msg)
        else:
            await client.send_message(client.get_channel(channel),msg)
    except Exception as e:
        msg = await client.send_message(message.channel,MESG.get('abuse_error','Error.'))
        asyncio.ensure_future(message_timeout(msg, 40))

@register('perms',owner=True)
async def perms(message,*args):
    """List permissions available to this  bot"""
    member = message.server.get_member(message.mentions[0].id if len(message.mentions) > 0 else client.user.id)
    perms = message.channel.permissions_for(member)
    perms_list = [' '.join(w.capitalize() for w in x[0].split('_')).replace('Tts','TTS') for x in perms if x[1]]

    msg = await client.send_message(message.channel, "**Perms for {user.name} in {server.name}:** ({1.value})\n```{0}```".format('\n'.join(perms_list),perms,user=member,server=message.server))
    asyncio.ensure_future(message_timeout(msg, 120))

@register('kick','@<mention users>',owner=True)
async def kick(message,*args):
    """Kicks the specified user from the server"""
    if len(message.mentions) < 1:
        return False

    if message.channel.is_private:
        msg = await client.send_message(message.channel,'Users cannot be kicked/banned from private channels.')
        asyncio.ensure_future(message_timeout(msg, 40))
        return

    if not message.channel.permissions_for(message.server.get_member(client.user.id)).kick_members:
        msg = await client.send_message(message.channel, message.author.mention + ', I do not have permission to kick users.')
        asyncio.ensure_future(message_timeout(msg, 40))
        return

    members = []

    if not message.channel.is_private and message.channel.permissions_for(message.author).kick_members:
        for member in message.mentions:
            if member != message.author:
                try:
                    await client.kick(member)
                    members.append(member.name)
                except:
                    pass
            else:
                msg = await client.send_message(message.channel, message.author.mention + ', You should not kick yourself from a channel, use the leave button instead.')
                asyncio.ensure_future(message_timeout(msg, 40))
    else:
        msg = await client.send_message(message.channel, message.author.mention + ', I do not have permission to kick users, or this is a private message channel.')
        asyncio.ensure_future(message_timeout(msg, 40))

    msg = await client.send_message(message.channel,'Successfully kicked user(s): `{}`'.format('`, `'.join(members)))
    asyncio.ensure_future(message_timeout(msg, 60))

@register('ban','@<mention users>',owner=True)
async def ban(message,*args):
    """Bans the specified user from the server"""
    if len(message.mentions) < 1:
        return False

    if message.channel.is_private:
        msg = await client.send_message(message.channel,'Users cannot be kicked/banned from private channels.')
        asyncio.ensure_future(message_timeout(msg, 40))
        return

    if not message.channel.permissions_for(message.server.get_member(client.user.id)).ban_members:
        msg = await client.send_message(message.channel, message.author.mention + ', I do not have permission to ban users.')
        asyncio.ensure_future(message_timeout(msg, 40))
        return

    members = []

    if message.channel.permissions_for(message.author).ban_members:
        for member in message.mentions:
            if member != message.author:
                try:
                    await client.ban(member)
                    members.append(member.name)
                except:
                    pass
            else:
                msg = await client.send_message(message.channel, message.author.mention + ', You should not ban yourself from a channel, use the leave button instead.')
                asyncio.ensure_future(message_timeout(msg, 40))
    else:
        msg = await client.send_message(message.channel, message.author.mention + ', I do not have permission to ban users, or this is a private message channel.')
        asyncio.ensure_future(message_timeout(msg, 40))

    msg = await client.send_message(message.channel,'Successfully banned user(s): `{}`'.format('`, `'.join(members)))
    asyncio.ensure_future(message_timeout(msg, 30))

@register('bans',alias='bannedusers')
@register('bannedusers')
async def banned_users(message,*args):
    """List users that have been banned from this server"""
    bans = await client.get_bans(message.server)

    if message.channel.is_private:
        msg = await client.send_message(message.channel,'Users cannot be kicked/banned from private channels.')
        asyncio.ensure_future(message_timeout(msg, 40))
        return

    str = ''
    for user in bans:
        str += "• {0.mention} (`{0.name}#{0.discriminator}`): [`{0.id}`]\n".format(user)

    embed = discord.Embed(title="Banned users in {0.name}".format(message.server),color=colour(message),description=str)
    msg = await client.send_message(message.channel,embed=embed)
    asyncio.ensure_future(message_timeout(msg, 60))

@register('fkoff',owner=True,alias='restart')
@register('restart',owner=True)
async def fkoff(message,*args):
    """Restart the bot"""
    logger.info('Stopping')
    await client.send_message(message.channel, MESG.get('shutdown','Shutting down.'))

    await client.logout()

    try:
        sys.exit()
    except Exception as e:
        logger.exception(e)
        pass

@register('calc','<expression>',rate=1,alias='maths')
@register('maths','<expression>',rate=1)
async def do_calc(message,*args):
    """Perform mathematical calculation: numbers and symbols (+-*/) allowed only"""
    logger.info('Calc')

    if len(args) < 1:
        return False

    maths = ''.join(args)

    if (re.findall('[^0-9\(\)\/\*\+-\.]+',maths) != []):
        await client.send_message(message.channel, MESG.get('calc_illegal','Illegal chars in {0}').format(maths))

    else:
        logger.info(' -> ' + str(maths))
        try:
            await client.send_message(message.channel,'`{} = {}`'.format(maths,calculate(maths)))
        except Exception as e:
            logger.exception(e)
            await client.send_message(message.channel, MESG.get('maths_illegal','Error in {0}').format(maths))

"""Utility functions"""
def colour(message=None):
    """Return user's primary role colour"""
    try:
        if message:
            return sorted([x for x in message.author.roles if x.colour != discord.Colour.default()], key=lambda x: -x.position)[0].colour
    except:
        pass

    return discord.Colour.default()

async def log_exception(e,location=None):
    """Log exceptions nicely"""
    try:
        exc = ''.join(traceback.format_exception(None, e, e.__traceback__).format(chain=True))
        exc = [exc[i:i+2000-6] for i in range(0, len(exc), 2000-6)]
        await client.send_message('257152358490832906', 'Error ' + ('in `{}`:'.format(location) if location else 'somewhere:'))
        for i,ex in enumerate(exc):
            await client.send_message('257152358490832906','```{:.1994}```'.format(ex))
    except:
        pass

async def message_timeout(message,timeout):
    """Deletes the specified message after the allotted time has passed"""
    if timeout > 0:
        await asyncio.sleep(timeout)

    await client.delete_message(message)

"""Reminders system"""
def get_reminder(invoke_time):
    """Returns reminder with specified invoke_time"""
    invoke_time = int(invoke_time)
    for rem in reminders:
        if rem['invoke_time'] == invoke_time:
            return rem

    return None

async def do_reminder(client, invoke_time):
    """Schedules and executes reminder"""
    cancel_ex = None
    try:
        reminder = get_reminder(invoke_time)
        wait = reminder['time']-int(time.time())
        if wait > 0:
            await asyncio.sleep(wait)
        else:
            chan = client.get_channel(reminder['channel_id'])
            await client.send_message(chan, 'The next reminder in channel ' + chan.name + ' is delayed by approximately ' + str(math.ceil(-wait/60.0)) + ' minutes, this is due to a bot fault')

        #get again to sync
        reminder = get_reminder(invoke_time)
        reminder['cancelled'] = True
        logger.info('Reminder ready')
        logger.info(' -> ' + reminder['user_mention'] + ': ' + reminder['message'])

        await client.send_message(client.get_channel(reminder['channel_id']), reminder['user_mention'] + ': ' + reminder['message'])
    except asyncio.CancelledError as e:
        cancel_ex = e
        reminder = get_reminder(invoke_time)
        if reminder['cancelled']:
            logger.info(' -> reminder ' + str(invoke_time) + ' cancelled')
            await client.send_message(client.get_channel(reminder['channel_id']), 'Reminder for '+reminder['user_name']+' in '+str(reminder['time']-int(time.time()))+' secs cancelled')
        else:
            logger.info(' -> reminder ' + str(invoke_time) + ' removed')

    if reminder['cancelled']:
        reminders.remove(reminder)

    save_reminders()

    if cancel_ex:
        raise cancel_ex

"""Exit procedure"""
@atexit.register
def save_reminders():
    """Save all in-memory reminders to file"""
    str = ''
    rems = []
    for rem in reminders[:]:
        rems.append({'user_name':rem['user_name'], 'user_mention':rem['user_mention'], 'invoke_time':rem['invoke_time'], 'time':rem['time'], 'channel_id':rem['channel_id'], 'message':rem['message'], 'is_cancelled':rem['is_cancelled']})
    for rem in rems:
        rem['task'] = None
        str += json.dumps(rem, sort_keys=True, skipkeys=True) + '\n'
    with open(CONF.get('dir_pref','/home/shwam3/')+'reminders.txt', 'w') as file:
        file.write(str)

"""Load reminders from file into memory"""
reminders = []
if os.path.isfile(CONF.get('dir_pref','/home/shwam3/')+'reminders.txt'):
    with open(CONF.get('dir_pref','/home/shwam3/')+'reminders.txt') as file:
        for line in file:
            try:
                reminders.append(json.loads(line))
            except json.decoder.JSONDecodeError as e:
                logger.error('JSON Error:')
                logger.exception(e)

"""Import definition overrides"""
special_defs = {}
if os.path.isfile(CONF.get('dir_pref','/home/shwam3/')+'special_defs.txt'):
    with open(CONF.get('dir_pref','/home/shwam3/')+'special_defs.txt') as file:
        for line in file:
            if line.find(':') < 0:
                continue
            line = line.split(':',1)
            special_defs[line[0].lower()] = line[1].replace('\n','')

"""Update bot status: "Playing Wikipedia: Albert Einstein"""
async def update_status():
    try:
        await client.change_presence(game=discord.Game(name='Wikipedia: ' + wikipedia.random(pages=1)),afk=False,status=None)
        await asyncio.sleep(60)
        asyncio.ensure_future(update_status())
    except:
        pass

"""Locate OAuth token"""
token = CONF.get('token',None)
if not token:
    with open(CONF.get('dir_pref','/home/shwam3/')+'tokens.txt') as file:
        token = file.read().splitlines()[0]

"""Run program"""
if __name__ == '__main__':
    try:
        #service = build('translate', 'v2', developerKey=CONF.get('gapi_key',''))
        client.run(token, bot=True)
        logging.shutdown()
    except Exception as e:
        logging.error(e)
