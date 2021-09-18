import sys, traceback
import time
import datetime

# https://github.com/ericsomdahl/python-bittrex
# from bittrex.bittrex import Bittrex
# https://github.com/sammchardy/python-binance
# from binance.client import Client
# https://github.com/kroitor/ccxt
import ccxt
from ccxt import ExchangeError, NotSupported, ExchangeNotAvailable, RequestTimeout


class TradingInterfaceReal:
    errorNoFund = 'ErrorNoFund'

    def __init__(self):
        self.testing = False
        self.id = ""
        self.exchange = None
        self.cachedOrderBook = {}
        self.cachedTickers = None
        self.lastTimeTickerRefreshed = datetime.datetime.now()
        self.cachedBalances = None
        self.leverage = {}

    def loadMarkets(self):
        return self.exchange.load_markets()

    def loadMarket(self, symbol):
        markets = self.loadMarkets()
        if symbol in markets:
            return markets[symbol]

        return {}

    def getPrecision(self, symbol):
        market = self.loadMarket(symbol)
        if 'step' in market:
            return market['step']
        elif 'precision' in market:
            return pow(10, -market['precision']['price'])

        return None

    def getBalance(self):
        balances = None

        try:
            balances = self.exchange.fetch_balance()
            self.cachedBalances = balances
        except:
            e = sys.exc_info()[0]
            print("Error getBalance: " + self.id + " " + str(e))

        return balances

    def getBalanceForCoin(self, coin):
        # self.sleep()
        balances = self.getBalance()
        balance = 0
        if balances != None and coin != None and coin in balances and 'free' in balances[coin]:
            balance = balances[coin]['free']
        # self.sleep()
        return balance
    
    def getCachedBalanceForCoin(self, coin, type = 'free'):
        balance = 0
        if self.cachedBalances != None and coin != None and coin in self.cachedBalances and type in self.cachedBalances[coin]:
            balance = self.cachedBalances[coin][type]
        return balance

    def getBalanceForEthBtc(self):
        self.sleep()
        balances = self.getBalance()
        balanceEth = 0
        balanceBtc = 0
        if balances != None:
            if 'ETH' in balances and 'free' in balances['ETH']:
                balanceEth = balances['ETH']['free']
            if 'BTC' in balances and 'free' in balances['BTC']:
                balanceEth = balances['BTC']['free']
        self.sleep()
        return balanceEth, balanceBtc

    def sleep(self):
        time.sleep(1)

    # time.sleep(self.exchange.rateLimit / 1000 * 2)

    def setLeverage(self, symbol, leverage):
        self.leverage[symbol] = leverage
        #result = None

        #try:
            #self.exchange.private_post_position_leverage({"symbol": symbol, "leverage": str(leverage)})
        #except:
            #e = sys.exc_info()[0]
            #print("Error setLeverage: " + str(e))

        #print(result)
        #return result

    def createOrder(self, symbol, type, side, amount, price, params):
        print("createOrder: " + symbol + " type:" + type + " side " + side + " amount " + str(amount) + " price: " + str(price))

        result = None

        try:
            result = self.exchange.create_order(symbol, type, side, amount, price, params)
        except ExchangeError as err:
            e = sys.exc_info()[0]
            print("Error createOrder: " + str(err))
            if 'InsufficientFunds' in str(e):
                return TradingInterfaceReal.errorNoFund
        except:
            e = sys.exc_info()[0]
            print("Error createOrder: " + str(e))

        print(result)
        return result

    def buy(self, symbol, type, amount, price):
        params = {}
        
        if type == 'market':
            amountToBuy = int(amount / price)
            if amountToBuy == 0:
                amountToBuy = float(amount / price)
    
            # make sure the amount to buy can be divided by lot
            market = self.loadMarket(symbol)
            if 'lot' in market:
                amountToBuy = amountToBuy - (amountToBuy % market['lot'])
                
            return self.createOrder(symbol, 'market', 'buy', amountToBuy, price, {})
        elif type == 'limit':
            return self.buyLimit(symbol, amount, price)

        return None

    def buyLimit(self, symbol, amount, price):
        result = None
        amountToBuy = int(amount / price)
        if amountToBuy == 0:
            amountToBuy = float(amount / price)

        # make sure the amount to buy can be divided by lot
        market = self.loadMarket(symbol)
        if 'lot' in market:
            amountToBuy = amountToBuy - (amountToBuy % market['lot'])

        if symbol in self.leverage:
            amountToBuy *= self.leverage[symbol];

        print("buyLimit: %s, amountToBuy: %.6f, price: %.8f" % (symbol, amountToBuy, price))

        try:
            result = self.exchange.create_limit_buy_order(symbol, amountToBuy, price)
        # except (ExchangeNotAvailable, RequestTimeout) as err:
        # time.sleep(5)
        # return self.buyLimit(symbol, amount, price)
        except ExchangeError as err:
            errorMessage = str(err)
            print("ExchangeError buyLimit: " + errorMessage)
            if 'Insufficient funds' in errorMessage:
                return TradingInterfaceReal.errorNoFund
        except:
            e = sys.exc_info()[0]
            print("Error buyLimit: " + str(e))

            print(result)

        if result != None and 'info' in result and 'ExecutionReport' in result['info']:
            if result['info']['ExecutionReport']['execReportType'] == 'rejected':
                print('Order rejected: ' + result['info']['ExecutionReport']['orderRejectReason'])
                return None

        return result

    def sell(self, symbol, type, amount, price):
        if type == 'market':
            return self.createOrder(symbol, 'market', 'sell', amount, price, {})
        elif type == 'limit':
            return self.sellLimit(symbol, amount, price)

        return None

    def sellLimit(self, symbol, amount, price):
        result = None
        print("sellLimit: " + symbol + " amount:" + str(amount) + " price: " + str(price))

        try:
            result = self.exchange.create_limit_sell_order(symbol, amount, price)
        except ExchangeError as err:
            e = sys.exc_info()[0]
            if 'InsufficientFunds' in str(e):
                return TradingInterfaceReal.errorNoFund
        except:
            e = sys.exc_info()[0]
            print("Error sellLimit: " + str(e))

        return result

    def getTicker(self, symbol):
        try:
            ticker = self.exchange.fetch_ticker(symbol)
        except:
            e = sys.exc_info()[0]
            print("Error getTicker: " + str(e))
            return None

        return ticker

    def getTickers(self):
        try:
            self.lastTimeTickerRefreshed = datetime.datetime.now()
            tickers = self.exchange.fetch_tickers()
            self.cachedTickers = tickers
        except:
            e = sys.exc_info()[0]
            print("Error getTickers: " + str(e))
            return None

        return tickers

    def setExchange(self, id):
        print("oo")
        
    def setExchangeFullDetails(self, id, key, secret, password=None):
        verbose = False
        exchange = None

        print('Set exchange: ' + id)
        self.id = id

        if id == "poloniex":
            exchange = ccxt.poloniex({'verbose': verbose, 'apiKey': key, 'secret': secret})
        if id == "bithumb":
            exchange = ccxt.bithumb({'verbose': verbose, 'apiKey': key, 'secret': secret})
        elif id == "binance":
            exchange = ccxt.binance({'verbose': verbose, 'apiKey': key, 'secret': secret, 'options': {'adjustForTimeDifference': True}})
        elif id == "binanceusdm":
            exchange = ccxt.binanceusdm({'verbose': verbose, 'apiKey': key, 'secret': secret})
        elif id == "bittrex":
            exchange = ccxt.bittrex({'verbose': verbose, 'apiKey': key, 'secret': secret})
        elif id == "kraken":
            exchange = ccxt.kraken({'verbose': verbose, 'apiKey': key, 'secret': secret})
        elif id == "hitbtc":
            exchange = ccxt.hitbtc({'verbose': verbose, 'apiKey': key, 'secret': secret})
        elif id == "kucoin":
            exchange = ccxt.kucoin({'verbose': verbose, 'apiKey': key, 'secret': secret, 'password': password})
        elif id == "bitmex":
            exchange = ccxt.bitmex({'verbose': verbose, 'apiKey': key, 'secret': secret})

        self.exchange = exchange

    def getCurrentExchangeId(self):
        if self.exchange == None:
            return "None"
        
        return self.exchange.id

    # side is 'buy' or 'sell'
    def cancelOrdersForSymbol(self, symbol=None, side='both'):
        print("cancelOrdersForSymbol " + str(symbol))
        try:
            orders = self.exchange.fetch_open_orders(symbol)
            for order in orders:
                if side == 'both' or order['side'] == side:
                    self.cancelOrder(order['id'])
        except:
            e = sys.exc_info()[0]
            print("Error: " + str(e))
            return False

        return True

    def cancelOrder(self, orderId):
        print("Cancel order " + str(orderId))
        try:
            self.exchange.cancel_order(orderId)
        except (ExchangeNotAvailable, RequestTimeout) as err:
            time.sleep(5)
            return self.cancelOrder(orderId)
        except:
            e = sys.exc_info()[0]
            print("Error: " + str(e))
            return False

        return True

    def getOrders(self):
        orders = None
        try:
            orders = self.exchange.fetch_ordersChris()
        except NotSupported as err:
            print("NotSupported: " + str(err))
        except ExchangeError as err:
            print("ExchangeError: " + str(err))
        except:
            e = sys.exc_info()[0]
            print("Error: " + str(e))

        return orders

    def getOrderById(self, id, symbol=None):
        order = None
        try:
            order = self.exchange.fetch_order(id, symbol)
        except NotSupported as err:
            print("NotSupported: " + str(err))
        except ExchangeError as err:
            print("ExchangeError: " + str(err))
        except TypeError as err:
            print("TypeError: " + str(err))
        except TimeoutError as err:
            print("TimeoutError: " + str(err))
        except:
            e = sys.exc_info()[0]
            print("Error: " + str(e))

        return order

    def getClosedOrder(self, symbol):
        order = None
        try:
            order = self.exchange.fetch_closed_orders(symbol)
        except NotSupported as err:
            print("NotSupported: " + str(err))
        except ExchangeError as err:
            print("ExchangeError: " + str(err))
        except TypeError as err:
            print("TypeError: " + str(err))
        except TimeoutError as err:
            print("TimeoutError: " + str(err))
        except:
            e = sys.exc_info()[0]
            print("Error: " + str(e))

        return order

    def getOrderIdFromResult(self, result):
        return result['id']

    def resetOrderBookCached(self):
        self.cachedOrderBook = {}

    def getOrderBook(self, symbol, useCachedVersionIfExists=False):
        if useCachedVersionIfExists and self.cachedOrderBook != None and symbol in self.cachedOrderBook and self.cachedOrderBook[symbol] != None:
            return self.cachedOrderBook[symbol]

        orderBook = None
        try:
            orderBook = self.exchange.fetch_order_book(symbol, {'depth': 15})
        except NotSupported as err:
            print("NotSupported: " + str(err))
        except ExchangeError as err:
            print("ExchangeError: " + str(err))
        except:
            e = sys.exc_info()[0]
            print("Error: " + str(e))

        self.cachedOrderBook[symbol] = orderBook
        return orderBook

    def getHistory(self, symbol, timeFrame):
        history = None
        if self.exchange.hasFetchOHLCV:
            try:
                history = self.exchange.fetch_ohlcv(symbol, timeFrame)
            except:
                e = sys.exc_info()[0]
                print("Error: " + str(e))

        return history
