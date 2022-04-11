class GOIFException(Exception):
    def __init__(self, exc_name):
        self.name = exc_name


class GOIFError(Exception):
    def __init__(self, msg):
        self.msg = msg
        super().__init__(msg)
