from telegram.ext.dispatcher import Dispatcher
from telegram import TelegramError
from threading import Event


class BlockDispatcher(Dispatcher):
    def __init__(self, updater, user_manager):
        # Build a new dispatcher based on the same settings as we get from the
        # updater.
        # TODO Probably shouldn't hard code workers but eh.
        super().__init__(updater.bot,
                         updater.update_queue,
                         4,
                         Event())
        self.um = user_manager
        # Replace the updater's dispatcher with this one
        updater.dispatcher = self

    def processUpdate(self, update):
        # An error happened while polling
        if isinstance(update, TelegramError):
            self.dispatchError(None, update)
        if self.um.is_blocked(update):
            return
        super().processUpdate(update)
