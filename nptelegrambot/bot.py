from telegram.ext import Updater, MessageHandler, Filters, CommandHandler
from .permissioncommandhandler import PermissionCommandHandler
from .users import UserManager
from .conversations import ConversationManager, ConversationHandler
from .groups import GroupManager
from threading import Thread
import argparse
import os
import logging
from functools import partial


class NPTelegramBot(object):
    FLAGS = ["admin", "def_edit", "user_flags"]

    def __init__(self, dbdir, tg_token):
        if not dbdir or not os.path.isdir(dbdir):
            print("Valid database directory required!")
            raise RuntimeError()
        self.logger = logging.getLogger(__name__)
        self.updater = Updater(token=tg_token)
        self.dispatcher = self.updater.dispatcher
        self.conversations = ConversationManager()
        self.users = UserManager(dbdir)
        self.groups = GroupManager(dbdir)

        # Make sure the message handlers are in different groups so they are
        # always run
        self.dispatcher.add_handler(MessageHandler([Filters.text],
                                                   self.handle_message), group=1)

        # Default commands These all require private message by default, just
        # so they don't possibly spam groups.
        self.dispatcher.add_handler(PermissionCommandHandler('start',
                                                             [self.require_privmsg],
                                                             self.handle_help))
        self.dispatcher.add_handler(PermissionCommandHandler('help',
                                                             [self.require_privmsg],
                                                             self.handle_help))
        self.dispatcher.add_handler(PermissionCommandHandler('settings',
                                                             [self.require_privmsg],
                                                             self.handle_help))
        self.dispatcher.add_handler(CommandHandler('cancel',
                                                   self.handle_cancel))

        # Admin commands
        self.dispatcher.add_handler(PermissionCommandHandler('userlist',
                                                             [self.require_privmsg,
                                                              partial(self.require_flag, flag="admin")],
                                                             self.users.show_list))

        self.dispatcher.add_handler(ConversationHandler('useraddflag',
                                                        [self.require_privmsg,
                                                         partial(self.require_flag, flag="admin")],
                                                        self.users.add_flag))

        self.dispatcher.add_handler(ConversationHandler('userrmflag',
                                                        [self.require_privmsg,
                                                         partial(self.require_flag, flag="admin")],
                                                        self.users.remove_flag))

        self.dispatcher.add_handler(ConversationHandler('groupadd',
                                                        [self.require_privmsg,
                                                         partial(self.require_flag, flag="admin")],
                                                        self.groups.add_group))

        self.dispatcher.add_handler(ConversationHandler('grouprm',
                                                        [self.require_privmsg,
                                                         partial(self.require_flag, flag="admin")],
                                                        self.groups.rm_group))

        self.dispatcher.add_handler(PermissionCommandHandler('outputcommands',
                                                             [self.require_privmsg,
                                                              partial(self.require_flag, flag="admin")],
                                                             self.output_commands))

        # On errors, just print to console and hope someone sees it
        self.dispatcher.add_error_handler(self.handle_error)

    def handle_help(self, bot, update):
        help_text = ["Hi! I'm an NP Telegram Bot! If I'm displaying this message, it means whoever wrote me didn't override the handle_help function. They should do that!"]
        bot.sendMessage(update.message.chat.id,
                        "\n".join(help_text),
                        parse_mode="HTML",
                        disable_web_page_preview=True)

    def handle_error(self, bot, update, error):
        # TODO Add ability for bot to message owner with stack traces
        self.logger.warn("Exception thrown! %s", self.error)

    def try_register(self, bot, update):
        user_id = update.message.from_user.id
        if not self.users.is_valid_user(user_id):
            self.users.register(bot, update)
        # Always returns true, as running any command will mean the user is
        # registered. We just want to make sure they're in the DB so flags can
        # be added if needed.
        return True

    def require_group(self, bot, update):
        # Special Case: If the bot has no users yet, we need to let the first
        # user register so they can be an admin. After that, always require
        # membership
        if self.users.get_num_users() == 0:
            return True
        if len(self.groups.get_groups()) == 0:
            return True
        user_id = update.message.from_user.id
        if not self.groups.user_in_groups(bot, user_id):
            bot.sendMessage(update.message.chat.id,
                            text="Please join a group I'm in to use this command!")
            return False
        return True

    # When used with PermissionCommandHandler, Function requires currying with
    # flag we want to check for.
    def require_flag(self, bot, update, flag):
        user_id = update.message.from_user.id
        if not self.users.is_valid_user(user_id) or not self.users.has_flag(user_id, flag):
            bot.sendMessage(update.message.chat.id,
                            text="You do not have the required permissions to run this command.")
            return False
        return True

    def require_privmsg(self, bot, update):
        if update.message.chat.id < 0:
            bot.sendMessage(update.message.chat.id,
                            reply_to_message_id=update.message.id,
                            text="Please message that command to me. Only the following commands are allowed in public chats:\n- /def")
            return False
        return True

    def output_commands(self, bot, update):
        command_str = ""
        for m in self.modules:
            command_str += m.commands() + "\n"
        bot.sendMessage(update.message.chat.id,
                        text=command_str)

    def handle_message(self, bot, update):
        # Ignore messages from groups
        if update.message.chat.id < 0:
            return
        if self.conversations.check(bot, update):
            return
        self.try_register(bot, update)
        self.handle_help(bot, update)

    def handle_cancel(self, bot, update):
        if update.message.chat.id < 0:
            return
        if not self.conversations.cancel(bot, update):
            bot.sendMessage(update.message.chat.id,
                            text="Don't have anything to cancel!")
            self.handle_help(bot, update)
            return
        bot.sendMessage(update.message.chat.id,
                        text="Command canceled!")

    def start_loop(self):
        self.updater.start_polling()
        self.updater.idle()

    def shutdown(self):
        pass


class NPTelegramBotCLI(NPTelegramBot):
    def __init__(self):
        parser = argparse.ArgumentParser()
        parser.add_argument("-d", "--dbdir", dest="dbdir",
                            help="Directory for pickledb storage")
        parser.add_argument("-r", "--rhost", dest="rhost",
                            help="Host for redis db")
        parser.add_argument("-p", "--rpass", dest="rpass",
                            help="Password for redis db")
        parser.add_argument("-t", "--token", dest="token_file",
                            help="File containing telegram API token")
        args = parser.parse_args()

        if not args.token_file:
            print("Token file argument required!")
            parser.print_help()
            raise RuntimeError()

        try:
            with open(args.token_file, "r") as f:
                tg_token = f.readline().strip()
        except:
            print("Cannot open token file!")
            raise RuntimeError()

        if (not args.dbdir or not os.path.isdir(args.dbdir)) and (not rhost and not rpass):
            print("Valid database directory or host required!")
            parser.print_help()
            raise RuntimeError()

        super().__init__(args.dbdir, tg_token)#rhost, rpass, tg_token)


class NPTelegramBotThread(NPTelegramBot):
    def __init__(self, dbdir, tg_token):
        super().__init__(dbdir, tg_token)
        # Steal the queue from the updater.
        self.update_queue = self.updater.update_queue

        # Start the thread
        self.thread = Thread(target=self.dispatcher.start, name='dispatcher')
        self.thread.start()

    def add_update(self, update):
        self.update_queue.put(update)

    def shutdown(self):
        self.thread.join(1)
        super().shutdown()

