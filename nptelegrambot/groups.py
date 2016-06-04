from .base import NPModuleBase


class ChatRedisTransactions(object):
    def __init__(self, redis):
        "docstring"
        self.redis = redis

    def add_chat(self, chat_id, chat_title, chat_username):
        self.redis.hmset(chat_id, {"id": chat_id,
                                   "title": chat_title,
                                   "username": chat_username})

    def set_chat_title(self, chat_id, chat_title):
        self.redis.hset(chat_id, "title", chat_title)

    def set_chat_username(self, chat_id, chat_username):
        self.redis.hset(chat_id, "username", chat_username)

    def get_chat(self, chat_id):
        return self.redis.hgetall(chat_id)

    def get_chats(self):
        chats = self.redis.hkeys("chat-status")
        pipe = self.redis.pipeline()
        for c in chats:
            pipe.hgetall(c)
        return pipe.execute()

    def get_chat_ids(self):
        return self.redis.hkeys("chat-status")

    def set_chat_id(self, old_chat_id, new_chat_id):
        # In case we switch from group to supergroup. Annoying!
        pass

    def update_chat_size(self, chat_id, chat_size):
        self.redis.hset(chat_id, "size", chat_size)
        self.redis.hset("chat-size", chat_id, chat_size)

    def update_chat_status(self, chat_id, chat_status):
        self.redis.hset(chat_id, "status", chat_status)
        self.redis.hset("chat-status", chat_id, chat_status)

    def get_chat_flag_key(self, chat_id):
        return "{0}:flags".format(chat_id)

    def get_chat_flags(self, chat_id):
        return self.redis.smembers(self.get_chat_flag_key(chat_id))

    def add_chat_flag(self, chat_id, flag):
        self.redis.sadd(self.get_chat_flag_key(chat_id), flag)

    def get_flags(self):
        self.redis.smembers("chat-flags")

    def add_flag(self, flag):
        self.redis.sadd("chat-flags", flag)

    def remove_flag(self, flag):
        self.redis.srem("chat-flags", flag)


class GroupManager(NPModuleBase):
    def __init__(self, redis):
        super().__init__(__name__)
        self.trans = ChatRedisTransactions(redis)
        # Just always add the block flag. Doesn't matter if it's already there.
        self.trans.add_flag("block")
        self.join_filters = []

    def process_status_update(self, bot, update):
        if update.message.new_chat_member:
            self.process_new_chat_member(bot, update)
        elif update.message.left_chat_member:
            self.process_left_chat_member(bot, update)
        elif update.message.group_chat_created:
            self.process_group_chat_created(bot, update)
        elif update.message.supergroup_chat_created:
            self.process_supergroup_chat_created(bot, update)
        elif update.message.migrate_from_chat_id:
            self.process_migrate_to_chat_id(bot, update)
        elif update.message.new_chat_title:
            self.process_new_chat_title(bot, update)

    def run_join_checks(self, bot, update):
        chat = update.message.chat
        for f in self.join_filters:
            if not f(bot, update):
                bot.sendMessage(chat.id,
                                text="Sorry, I can't be in this chat!")
                bot.leaveChat(chat.id)
                return False
        return True

    def process_new_chat_member(self, bot, update):
        # from will be user that invited member, if any
        # new_chat_member will be member that left
        chat = update.message.chat
        if update.message.new_chat_member.id != bot.id:
            chat_size = bot.getChatMembersCount(chat.id)
            self.trans.update_chat_size(chat.id, chat_size)
            return
        if not self.run_join_checks(bot, update):
            return
        self.trans.add_chat(chat.id, chat.title, chat.username)
        member_info = bot.getChatMember(chat.id, bot.id)
        self.trans.update_chat_status(chat.id, member_info["status"])
        chat_size = bot.getChatMembersCount(chat.id)
        self.trans.update_chat_size(chat.id, chat_size)

    def process_left_chat_member(self, bot, update):
        # from will be user that kicked member, if any
        # left_channel_member will be member that left
        # We have joined a new channel
        chat = update.message.chat
        if update.message.left_chat_member.id != bot.id:
            chat_size = bot.getChatMembersCount(chat.id)
            self.trans.update_chat_size(chat.id, chat_size)
            return
        chat = update.message.chat
        member_info = bot.getChatMember(chat.id, bot.id)
        self.trans.update_chat_status(chat.id, member_info["status"])

    def process_group_chat_created(self, bot, update):
        # Bot invited as a creating member of a group chat
        if not self.run_join_checks(bot, update):
            return

    def process_supergroup_chat_created(self, bot, update):
        # Bot invited as a creating member of a supergroup chat (does this happen?)
        if not self.run_join_checks(bot, update):
            return

    # migration is sent as both from_id and to_id. Both messages contain the
    # same information, so we can use that to update ourselves.
    def process_migrate_to_chat_id(self, bot, update):
        pass

    def process_new_chat_title(self, bot, update):
        chat = update.message.chat
        self.trans.set_chat_title(chat.id, chat.title)

    def broadcast(self, bot, update):
        bot.sendMessage(update.message.chat.id,
                        text="What message would you like to broadcast to groups I'm in?")
        (bot, update) = yield
        message = update.message.text
        chats = self.trans.get_chats()
        for c in chats:
            if c["status"] not in ["left", "kicked"]:
                try:
                    bot.sendMessage(c["id"],
                                    text=message)
                except:
                    # If we errored out, we've been kicked from the channel.
                    # Since telegram doesn't notify us we've been kicked, this
                    # is our only way to know. Update our status accordingly.
                    self.trans.update_chat_status(c["id"], "kicked")

    def add_join_filter(self, join_filter):
        self.join_filters.append(join_filter)

    def list_known_chats(self, bot, update):
        chats = self.get_chats()
        msg = "Groups I know about and my status in them:\n\n"
        for c in chats:
            msg += "{0} - {1}\n".format(c["title"], c["id"])
            msg += "- Status: {0}\n".format(c["status"])
            msg += "- Size: {0}\n\n".format(c["size"])
        bot.sendMessage(update.message.chat.id,
                        text=msg)

    def leave_chat(self, bot, update, block=False):
        while True:
            bot.sendMessage(update.message.chat.id,
                            text="Enter the id of the chat you'd like to leave/block, or /cancel.")
            (bot, update) = yield
            leave_id = update.message.text
            leave_chat = self.trans.get_chat(leave_id)
            if leave_chat is not None:
                break
            bot.sendMessage(update.message.chat.id,
                            text="Not a valid ID for a channel I'm in, try again!")
        bot.leaveChat(leave_chat["id"])
        if block:
            self.trans.add_chat_flag(leave_chat["id"], "block")

    @staticmethod
    def min_size_filter(bot, update, min_size):
        count = bot.get_chat_member_count(update.message.chat.id)
        return count >= min_size

    @staticmethod
    def max_size_filter(bot, update, max_size):
        count = bot.get_chat_member_count(update.message.chat.id)
        return count <= max_size

    def block_filter(self, bot, update):
        if "block" in self.trans.get_chat_flags(str(update.message.chat.id)):
            return False
        return True
