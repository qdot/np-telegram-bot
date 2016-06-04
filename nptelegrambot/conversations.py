from telegram import ReplyKeyboardHide
from .base import NPModuleBase
from .permissioncommandhandler import PermissionCommandHandler


class ConversationHandler(PermissionCommandHandler):
    def __init__(self, command, perm_checks, cm, callback, pass_args=False,
                 pass_update_queue=False):
        # Callbacks passed to this are actually generators, so reroute to our
        # own conversation manager.
        self.generator = callback
        self.cm = cm
        super().__init__(command,
                         perm_checks,
                         self.run_generator,
                         pass_args,
                         pass_update_queue)

    def run_generator(self, bot, update):
        c = self.generator(bot, update)
        c.send(None)
        self.cm.add(update, c)


class ConversationManager(NPModuleBase):
    def __init__(self):
        # Conversations only survive as long as the process, so no need to
        # pickledb here.
        super().__init__(__name__)
        # Conversation dictionary. Key will be user id for the conversation.
        # Value will get a generator object.
        self.conversations = {}

    def add(self, update, conversation):
        self.conversations[(update.message.chat.id,
                            update.message.from_user.id)] = conversation

    def check(self, bot, update):
        conv_id = (update.message.chat.id, update.message.from_user.id)
        if conv_id not in self.conversations.keys():
            return False
        try:
            # send only takes a single argument, so case up the current bot and
            # update in a tuple
            self.conversations[conv_id].send((bot, update))
        except StopIteration:
            self.cancel(bot, update)
        return True

    def cancel(self, bot, update, conv_ended=False):
        chat_id = update.message.chat.id
        user_id = update.message.from_user.id
        if (chat_id, user_id) not in self.conversations.keys():
            bot.sendMessage(update.message.chat.id,
                            text="Don't have anything to cancel!",
                            reply_markup=ReplyKeyboardHide())
            return False
        del self.conversations[(chat_id, user_id)]
        # Kill any currently displayed keyboard
        bot.sendMessage(update.message.chat.id,
                        text="Command finished!",
                        reply_markup=ReplyKeyboardHide())
        return True

    def shutdown(self):
        for (chat_id, c) in self.conversations:
            # Send a message here saying we're shutting down?
            pass
