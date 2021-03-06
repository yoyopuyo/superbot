from tradingInterfaceReal import TradingInterfaceReal

class TradingExchanges:
	def __init__(self):
		self.exchanges = {}

	def createExchange(self, id):
		tradingInterface = TradingInterfaceReal()
		tradingInterface.setExchange(id)
		tradingInterface.getTickers()
		self.exchanges[id] = tradingInterface
		return tradingInterface

	def createExchangeFullDetails(self, id, key, secret, password):
		tradingInterface = TradingInterfaceReal()
		tradingInterface.setExchangeFullDetails(id, key, secret, password)
		tradingInterface.getTickers()
		self.exchanges[id] = tradingInterface
		return tradingInterface

	def getExchange(self, id, createIfNeeded = True):
		id = id.lower()
		
		if id == 'capitalcom':
			id = 'naga'
			
		if id in self.exchanges:
			return self.exchanges[id]

		if createIfNeeded:
			return self.createExchange(id)
		
		return None



