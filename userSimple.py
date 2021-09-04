from typing import List

from tradingexchanges import TradingExchanges

class UserSimple:
    def __init__(self, userData = None):
        self.tradingExchanges = TradingExchanges()

        if userData is not None:
            self.id = userData['id']
            self.email = userData['email']
            self.exchanges = []
    
            self.exchangesDef = userData['exchangesDef']
    
            for exchange in self.exchangesDef:
                print("create exchange "+ exchange['id'])
                password = None
                if 'password' in exchange:
                    password = exchange['password']
                self.addExchange(exchange['id'], exchange['key'], exchange['secret'], password)

    def addExchange(self, id, key, secret, password):
        self.tradingExchanges.createExchangeFullDetails(id, key, secret, password)
        
    def hasExchange(self, id):
        return self.tradingExchanges.getExchange(id, False) != None
    
    def getExchange(self, id):
        return self.tradingExchanges.getExchange(id)

    def print(self):
        print(str(self.id) + ": " + self.email)
