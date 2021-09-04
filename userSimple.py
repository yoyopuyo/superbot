from typing import List

from tradingexchanges import TradingExchanges

class UserSimple:
    def __init__(self, logging, userData):
        self.logging = logging
        self.tradingExchanges = TradingExchanges(logging)

        self.id = userData['id']
        self.email = userData['email']
        self.exchanges = []

        self.exchangesDef = userData['exchangesDef']

        for exchange in self.exchangesDef:
            print("create exchange "+ exchange['id'])
            password = None
            if 'password' in exchange:
                password = exchange['password']
            self.tradingExchanges.createExchangeFullDetails(exchange['id'], exchange['key'], exchange['secret'], password)

    def hasExchange(self, id):
        return self.tradingExchanges.getExchange(id, False) != None
    
    def getExchange(self, id):
        return self.tradingExchanges.getExchange(id)

