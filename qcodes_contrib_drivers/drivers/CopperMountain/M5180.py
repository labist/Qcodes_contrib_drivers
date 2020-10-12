from . import M51xx

class M5180(M51xx.CMTxBase):
    def __init__(self, name, address, **kwargs):
        super().__init__(name, address,
                         min_freq=3e5, max_freq=18e9,
                         min_power=-50, max_power=10,
                         nports=1,
                         **kwargs)

