import logging


class NPModuleBase(object):
    def __init__(self, logger_name):
        self.logger = logging.getLogger(logger_name)

    def commands(self):
        return ""
