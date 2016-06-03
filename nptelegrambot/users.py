from telegram.ext import CommandHandler
from .base import NPModuleBase


class UserRedisTransactions(object):
    def __init__(self, redis):
        self.redis = redis
        self.flags = self.get_flags()
        if (self.flags is None or
            "admin" not in self.flags or
            "block" not in self.flags):
            self.add_flag("admin")
            self.add_flag("block")

    def user_flag_key(self, id):
        return "{0}:flags".format(id)

    def get_num_users(self):
        return self.redis.zcard("user-names")

    def is_valid_user(self, id):
        return len(self.get_user(id).keys()) > 0

    def get_user(self, id):
        return self.redis.hgetall(id)

    def add_flag(self, flag):
        self.redis.sadd("user-flags", flag)

    def remove_flag(self, flag):
        self.redis.srem("user-flags", flag)

    def get_flags(self):
        return self.redis.smembers("user-flags")

    def add_user_flag(self, id, flag):
        self.redis.sadd(self.user_flag_key(id), flag)

    def remove_user_flag(self, id, flag):
        self.redis.srem(self.user_flag_key(id), flag)

    def get_user_flags(self, id):
        return self.redis.smembers(self.user_flag_key(id))

    def add_user(self, id, username, firstname, lastname):
        self.redis.hmset(id, {"username": username,
                              "firstname": firstname,
                              "lastname": lastname})

    def remove_user(self, id):
        self.redis.delete(id)
        self.redis.delete("{0}:flags".format(id))


class UserManager(NPModuleBase):
    def __init__(self, store):
        super().__init__(__name__)
        self.trans = UserRedisTransactions(store)
        self.has_admin = True
        if self.trans.get_num_users() == 0:
            self.has_admin = False

    def register_with_dispatcher(self, dispatcher):
        dispatcher.add_handler(CommandHandler('register', self.register))
        dispatcher.add_handler(CommandHandler('profile_hide',
                                              self.set_hide_profile))
        dispatcher.add_handler(CommandHandler('profile_show',
                                              self.set_show_profile))

    def is_valid_user(self, user_id):
        return self.trans.is_valid_user(user_id)

    def register(self, bot, update):
        self.logger.debug("User registration requested")
        user = update.message.from_user
        user_id = str(user.id)
        # if user is already registered, stop here.
        if self.trans.is_valid_user(user_id):
            self.logger.debug("User already registered")
            return
        self.trans.add_user(user_id,
                            user.username,
                            user.first_name,
                            user.last_name)
        if not self.has_admin:
            bot.sendMessage(update.message.chat.id,
                            text="You're the first user, therefore you're the <b>admin</b>.",
                            parse_mode="HTML")
        self.trans.add_user_flag(user_id, "admin")

    def help(self, bot, update):
        return ""

    def commands(self):
        return ""

    def remove_flag(self, bot, update):
        while True:
            bot.sendMessage(update.message.chat.id,
                            text="Forward me a message from the user you want to add flags to, or /cancel.")
            (bot, update) = yield
            (user_id, user) = self.get_flag_edit_user(bot, update)
            if user_id is not None:
                break
        while True:
            bot.sendMessage(update.message.chat.id,
                            text="What is the name of the flag you would like to remove for %s?" % (user["username"]))
            # TODO: show permissions flag keyboard here
            (bot, update) = yield
            user_flag = update.message.text
            self.trans.remove_user_flag(user_id, user_flag)
            bot.sendMessage(update.message.chat.id,
                            text="Removed flag %s from %s" % (user_flag, user_name_or_id))

    def add_flag(self, bot, update):
        while True:
            bot.sendMessage(update.message.chat.id,
                            text="Forward me a message from the user you want to remove flags from, or /cancel.")
            (bot, update) = yield
            (user_id, user) = self.get_flag_edit_user(bot, update)
            if user_id is not None:
                break
        while True:
            bot.sendMessage(update.message.chat.id,
                            text="What is the name of the flag you would like to add for %s? If you're done, /cancel." % (user["username"]))
            # TODO: show permissions flag keyboard here
            (bot, update) = yield
            user_flag = update.message.text
            self.trans.add_user_flag(update.message.from_user.id, user_flag)
            bot.sendMessage(update.message.chat.id,
                            text="Added flag %s to %s" % (user_flag, user_name_or_id))

    def has_flag(self, user_id, flag):
        user_id = str(user_id)
        if flag in self.trans.get_user_flags(user_id):
            return True
        return False
