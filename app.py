import time
import threading
import os

from fileutils import FileUtils
from flask import Flask, request, abort, render_template
from mail import Mail
from userSimple import UserSimple
from s3FileUtils import S3FileUtils

ordersDataFileName = 'data/ordersData.txt'
configFileName = 'data/configTradingViewBot.txt'

processingAlert = False

config = {}
users = []
ordersData = []
saveToS3 = False
if os.getenv('save-to-s3', None) == "1":
    print("Load from s3")
    saveToS3 = True
    s3 = S3FileUtils()    
    
def getSymbolRightPart(symbol):
    if '/' in symbol:
        return symbol.split('/')[1]

    return None

def loadConfig():
    global config
    config = FileUtils.loadJsonFromFile(configFileName)

def loadUsers():
    global users
    users = []
    for i in range(1, 3):
        mail = os.getenv(str(i) + "-mail")
        if mail is not None:
            print(mail)
            user = UserSimple()
            user.id = str(i)
            user.email = mail
            
            for exchangeId in config["exchanges"]:
                if user.hasExchange(exchangeId) == False:
                    key = os.getenv(str(i) + "-" + exchangeId + "-key")
                    if key is not None:
                        secret = os.getenv(str(i) + "-" + exchangeId + "-secret")
                        password = os.getenv(str(i) + "-" + exchangeId + "-password")
                        user.addExchange(exchangeId, key, secret, password)
                    
            user.print()
            users.append(user)
        
    #for userData in config['users']:
        #user = UserSimple(userData)
        #users.append(user)


def loadOrdersData():
    global ordersData
    global saveToS3
    print("load orders " + str(saveToS3))
    if saveToS3:
        ordersData = s3.loadJsonFromFile('orders.json')
    else:
        ordersData = FileUtils.loadJsonFromFile(ordersDataFileName)

def saveOrdersData():
    global ordersData
    global saveToS3
    print("save orders " + str(saveToS3))
    
    if saveToS3:
        s3.saveJsonToFile('orders.json', ordersData)
    else:
        FileUtils.saveJsonToFile(ordersDataFileName, ordersData)

def getAlertConfig(alertId):
    if alertId in config['alerts']:
        return config['alerts'][alertId]

    return {}

def getAlertValue(exchangeId, symbol, alertId, itemId, default):
    cfg = getConfig(exchangeId, symbol)
    if 'alerts' in cfg and alertId in cfg['alerts'] and itemId in cfg['alerts'][alertId]:
        return cfg['alerts'][alertId][itemId]

    # find */symbol
    if '/' in symbol:
        wildcard = '*/' + symbol.split('/')[1]
        if wildcard in config[exchangeId] and 'alerts' in config[exchangeId][wildcard] and alertId in config[exchangeId][wildcard]['alerts'] and itemId in config[exchangeId][wildcard]['alerts'][
            alertId]:
            return config[exchangeId][wildcard]['alerts'][alertId][itemId]

    a = getAlertConfig(alertId)
    if itemId in a:
        return a[itemId]

    return default

def getOrderType(exchangeId, symbol, alertId):
    return getAlertValue(exchangeId, symbol, alertId, "orderType", "limit")

def getStrategyId(exchangeId, symbol, alertId):
    return getAlertValue(exchangeId, symbol, alertId, "strategyId", "")

def getQuantityPercent(exchangeId, symbol, alertId):
    return getAlertValue(exchangeId, symbol, alertId, "quantityPercent", 100)

def getKeepFreeCoins(exchangeId, symbol, alertId):
    return getAlertValue(exchangeId, symbol, alertId, "keepFreeCoins", False)

def getSendMail(exchangeId, symbol, alertId):
    return getAlertValue(exchangeId, symbol, alertId, "sendMail", True)

def getActionFromAlertType(exchangeId, symbol, alertId):
    return getAlertValue(exchangeId, symbol, alertId, "action", None)

def getConfig(exchangeId, symbol):
    if symbol in config[exchangeId]:
        return config[exchangeId][symbol]

    return {}

def getConfigValue(exchangeId, symbol, value, default):
    if symbol in config[exchangeId] and value in config[exchangeId][symbol]:
        return config[exchangeId][symbol][value]

    # find */symbol
    if '/' in symbol:
        wildcard = '*/' + symbol.split('/')[1]
        if wildcard in config[exchangeId] and value in config[exchangeId][wildcard]:
            return config[exchangeId][wildcard][value]

    return 0

def getConfigAmountToBuy(user, exchangeId, symbol, numBuyOrders, ordersInfo):
    amountToBuy = 0

    amountFirstBuyPercentOfBalance = getConfigValue(exchangeId, symbol, "amountFirstBuyPercentOfBalance", 0)

    if amountFirstBuyPercentOfBalance != 0:
        if numBuyOrders == 0:
            balance = getCachedBalance(user, exchangeId, symbol)
            print("balance " + str(balance) + " amountFirstBuyPercentOfBalance " + str(amountFirstBuyPercentOfBalance))
            amountToBuy = balance * (amountFirstBuyPercentOfBalance * 0.01)
        else:
            amountMultiplier = getConfigValue(exchangeId, symbol, "amountMultiplier", None)
            if amountMultiplier != None and ordersInfo != None and 'orders' in ordersInfo and len(ordersInfo['orders']) > 0:
                amountFirstBuy = float(ordersInfo['orders'][0]['amountSpent'])
                amountToBuy = amountFirstBuy * amountMultiplier[min(numBuyOrders, len(amountMultiplier) - 1)]
    else:
        amount = getConfigValue(exchangeId, symbol, "amount", 0)
        if isinstance(amount, list):
            amountToBuy = amount[min(numBuyOrders, len(amount) - 1)]
        else:
            amountToBuy = amount

    currency = getSymbolRightPart(symbol).lower()
    if currency == 'usd' or currency == 'usdt':
        amountToBuy = int(amountToBuy)

    return amountToBuy

def getCachedBalance(user, exchangeId, symbol, type='free'):
    return user.getExchange(exchangeId).getCachedBalanceForCoin(getSymbolRightPart(symbol), type)

def sendOrder(user, data):
    print(data)
    info = [x.strip() for x in data.split(',')]
    alertId = info[0]
    tickerId = info[1]
    tickerIdSplit = tickerId.split(':')
    exchangeId = tickerIdSplit[0].upper()
    symbol = tickerIdSplit[1].upper()
    if exchangeId == "CAPITALCOM":
        if 'USD' not in symbol:
            symbol = symbol + 'USD'
            symbol = symbol.replace("USD", "/USD")

    if 'PERP' in symbol:
        symbol = symbol.replace("PERP", "")
        if exchangeId == "BINANCE":
            exchangeId = "BINANCEUSDM"

    if user.hasExchange(exchangeId) == False:
        return

    exchange = user.getExchange(exchangeId)

    if '/' not in symbol:
        symbol = symbol.replace("USDT", "/USDT")
        if not symbol.startswith('BTC'):
            symbol = symbol.replace("BTC", "/BTC")
        if not symbol.startswith('ETH'):
            symbol = symbol.replace("ETH", "/ETH")
        if not symbol.startswith('BNB'):
            symbol = symbol.replace("BNB", "/BNB")
        if not symbol.startswith('KCS'):
            symbol = symbol.replace("KCS", "/KCS")
        symbol = symbol.replace("USDC", "/USDC")
        symbol = symbol.replace("BUSD", "/BUSD")

    price = float(info[2])
    if len(info) > 3:
        timeFrame = info[3]
    else:
        timeFrame = '?'

    action = getActionFromAlertType(exchangeId, symbol, alertId)
    strategyId = getStrategyId(exchangeId, symbol, alertId)

    if action == None:
        return

    if action == "mail":
        if getAlertValue(exchangeId, symbol, alertId, "deleteBuyOrdersFromDb", False):
            deleteBuyOrdersFromDb(user, exchangeId, tickerId, timeFrame, strategyId)
        Mail.sendMail(alertId, data, user.email)
        return

    if action == 'executeAlert':
        exAlert = getAlertValue(exchangeId, symbol, alertId, "executeAlert", None)
        exWhen = getAlertValue(exchangeId, symbol, alertId, "executeWhen", None)
        setupExecuteAlert(user, exchangeId, tickerId, timeFrame, strategyId, exAlert, exWhen)
        return

    side = ''
    if action == 'buy':
        side = 'buy'
    if action == 'sellAll' or action == 'sellBreakEven' or action == 'sellLadder':
        side = 'sell'

    if side == '':
        return

    orderType = getOrderType(exchangeId, symbol, alertId)

    if side == 'buy':
        maxSystems = getAlertValue(exchangeId, symbol, alertId, "maxSystems", 9999999)
        if getNumberSystemsForStrategy(user, exchangeId, strategyId) > maxSystems:
            print("Too many systems")
            return

        numBuyOrders = getNumberBuyOrders(user, exchangeId, tickerId, timeFrame, strategyId)

        minBalanceForFirstPurchaseFreePercentOfTotal = getConfigValue(exchangeId, symbol, "minBalanceForFirstPurchaseFreePercentOfTotal", 0)
        freeBalance = getCachedBalance(user, exchangeId, symbol)
        total = getCachedBalance(user, exchangeId, symbol, 'total')
        print("Free Balance " + str(freeBalance) + " total Balance " + str(total) + " minBalanceForFirstPurchaseFreePercentOfTotal " + str(minBalanceForFirstPurchaseFreePercentOfTotal))
        if minBalanceForFirstPurchaseFreePercentOfTotal != 0 and (1 - (total - freeBalance) / total) * 100 < minBalanceForFirstPurchaseFreePercentOfTotal:
            print("Not enough funds")
            return

        ordersInfo = getOrderData(user, exchangeId, tickerId, timeFrame, strategyId)
        amountToBuy = getConfigAmountToBuy(user, exchangeId, symbol, numBuyOrders, ordersInfo)

        if amountToBuy == 0:
            print("Buy 0, return")
            return

        print("amountToBuy " + str(amountToBuy))

        result = exchange.buy(symbol, orderType, amountToBuy, price)
        if result != None:
            orderId = exchange.getOrderIdFromResult(result)
            handleBuy(user, tickerId, exchangeId, timeFrame, strategyId, symbol, orderId, price, amountToBuy)
            error = ''
        else:
            error = ", error"

        if config['options']['sendMail'] and getSendMail(exchangeId, symbol, alertId):
            Mail.sendMail(action + ', bought ' + symbol + error + ", " + str(timeFrame) + ", Buy " + str(numBuyOrders + 1),
                          symbol + ' amountToBuy = ' + str(amountToBuy) + ', price = ' + str(price) + ', ' + orderType, user.email)
    elif side == 'sell':
        quantityPercent = getQuantityPercent(exchangeId, symbol, alertId)
        keepFreeCoins = getKeepFreeCoins(exchangeId, symbol, alertId)

        ordersInfo = getOrderData(user, exchangeId, tickerId, timeFrame, strategyId)
        if ordersInfo == None:
            print('No buy order found for ' + tickerId)
            return

        numberCoinsBought, totalSpent, breakEvenPrice = getOrdersInfo(exchange, ordersInfo)

        if action == 'sellBreakEven':
            price = breakEvenPrice

        cancelAllBuys(exchange, ordersInfo)

        if price == 0:
            return

        if numberCoinsBought <= 0:
            print('No coins to sell for ' + tickerId)
            return

        if quantityPercent == 100 and keepFreeCoins:
            toSell = numberCoinsBought * quantityPercent / 100
        else:
            toSell = numberCoinsBought * quantityPercent / 100

        totalToReceive = toSell * price
        gainPercent = (totalToReceive - totalSpent) / totalSpent
        if gainPercent >= 0:
            gainPercentStr = "+{:.2%}".format(gainPercent)
        else:
            gainPercentStr = "{:.2%}".format(gainPercent)

        result = exchange.sell(symbol, orderType, toSell, price)
        if result != None:
            handleSell(user, exchangeId, tickerId, timeFrame, strategyId)
            error = ''
        else:
            error = ", error"

        if config['options']['sendMail'] and getSendMail(exchangeId, symbol, alertId):
            Mail.sendMail(action + ': sold ' + symbol + ', ' + gainPercentStr + error + ", " + timeFrame, symbol + ', price = ' + str(price) + ', totalSpent = ' + str(totalSpent) +
                          ', numberCoinsBought = ' + str(numberCoinsBought) + ", coinsToSell = " + str(toSell) + ', quantityPercent = ' + str(quantityPercent) +
                          ', keepFreeCoins = ' + str(keepFreeCoins) + ', ' + orderType, user.email)

        if action == "sellLadder":
            startSellLadder(exchangeId, timeFrame, strategyId, symbol, alertId)


def startSellLadder(exchangeId, timeFrame, strategyId, symbol, alertId):
    print("")
    numberSteps = getAlertValue(exchangeId, symbol, alertId, "ladderSteps", 3)
    ladderEndPercent = getAlertValue(exchangeId, symbol, alertId, "ladderEndPercent", 3)


def setupExecuteAlert(user, exchangeId, tickerId, timeFrame, strategyId, executeAlert, executeWhen):
    ordersInfo = getOrderData(user, exchangeId, tickerId, timeFrame, strategyId)
    if ordersInfo == None:
        return

    ordersInfo['executeAlert'] = executeAlert
    ordersInfo['executeWhen'] = executeWhen
    saveOrdersData()

    tryLaunchAlert(user, exchangeId, tickerId, timeFrame, strategyId)


def tryLaunchAlert(user, exchangeId, tickerId, timeFrame, strategyId):
    ordersInfo = getOrderData(user, exchangeId, tickerId, timeFrame, strategyId)
    if ordersInfo == None:
        return

    if 'executeAlert' not in ordersInfo:
        return

    if 'executeWhen' not in ordersInfo:
        return

    executeAlert = None
    if ordersInfo['executeWhen'] == 'AllBuyOrdersClosedOrCanceled':
        for order in ordersInfo['orders']:
            if order['status'] != 'open':
                executeAlert = ordersInfo['executeAlert']

    if executeAlert != None:
        del ordersInfo['executeAlert']
        del ordersInfo['executeWhen']
        saveOrdersData()

        print("Launch Alert ------------------------------------")
        sendOrder(user, executeAlert + ',' + tickerId + ',0,' + str(timeFrame))


def getOrderData(user, exchangeId, tickerId, timeFrame, strategyId):
    if user.id in ordersData and exchangeId in ordersData[user.id]:
        for o in ordersData[user.id][exchangeId]:
            if o['ticker'] == tickerId and o['timeFrame'] == timeFrame and o['strategy'] == strategyId:
                return o

    return None


def getNumberBuyOrders(user, exchangeId, tickerId, timeFrame, strategyId):
    o = getOrderData(user, exchangeId, tickerId, timeFrame, strategyId)
    if o == None:
        return 0

    return len(o['orders'])


def cancelAllBuys(exchange, ordersInfo):
    for order in ordersInfo['orders']:
        if order['status'] == 'open' or order['status'] == '?':
            exchange.cancelOrder(order['orderId'])


def getOrdersInfo(exchange, ordersInfo):
    coins = 0
    totalSpent = 0
    breakEvenPrice = 99999999

    for order in ordersInfo['orders']:
        realOrder = exchange.getOrderById(order['orderId'], ordersInfo['symbol'])
        if realOrder == None:
            print("BuyOrder for " + ordersInfo['ticker'] + " with id " + str(order['orderId']) + " not found.")
        else:
            coins += realOrder['filled']
            totalSpent += (realOrder['filled'] * realOrder['price'])

    if coins > 0:
        breakEvenPrice = totalSpent / coins

    return coins, totalSpent, breakEvenPrice


def handleBuy(user, tickerId, exchangeId, timeFrame, strategyId, symbol, orderId, price, amountToBuy):
    o = getOrderData(user, exchangeId, tickerId, timeFrame, strategyId)
    if o == None:
        if user.id not in ordersData:
            ordersData[user.id] = {}
        if exchangeId not in ordersData[user.id]:
            ordersData[user.id][exchangeId] = []
        ordersData[user.id][exchangeId].append({'ticker': tickerId, 'symbol': symbol, 'timeFrame': timeFrame,
                                                'strategy': strategyId, 'orders': []})
        o = getOrderData(user, exchangeId, tickerId, timeFrame, strategyId)

    o['orders'].append({'orderId': orderId, 'status': 'open', 'time': 0, 'price': str(price), 'amountSpent': str(amountToBuy)})

    saveOrdersData()


def updateOrdersStatus(user):
    cancelBuyAfterMinutes = config['options']['cancelBuyAfterMinutes']

    for exchangeId in user.tradingExchanges.exchanges:
        if user.hasExchange(exchangeId):
            exchange = user.tradingExchanges.getExchange(exchangeId)
            exchange.getBalance()

    if user.id not in ordersData:
        return

    a = ordersData[user.id]
    changed = False
    for exchangeId in ordersData[user.id]:
        ordersForExchange = ordersData[user.id][exchangeId]
        for ordersInfo in ordersForExchange:
            for order in ordersInfo['orders']:
                if 'time' in order:
                    order['time'] += 1
                else:
                    order['time'] = 0

                if 'status' not in order:
                    order['status'] = 'open'

                if order['status'] == 'open':
                    realOrder = user.getExchange(exchangeId).getOrderById(order['orderId'], ordersInfo['symbol'])
                    if realOrder == None:
                        order['status'] = 'notFound'
                        changed = True
                    else:
                        if order['status'] is not realOrder['status']:
                            changed = True
                        order['status'] = realOrder['status']

                        if order['time'] >= cancelBuyAfterMinutes:
                            print("Order time elapsed: " + ordersInfo['ticker'])
                            user.getExchange(exchangeId).cancelOrder(order['orderId'])
                            order['status'] = 'canceled'
                            changed = True

                if changed:
                    saveOrdersData()

            tryLaunchAlert(user, exchangeId, ordersInfo['ticker'], ordersInfo['timeFrame'], ordersInfo['strategy'])

        # if realOrder['filled'] == 0:
        # del order
        # if len(ordersInfo['orders']) == 0:
        # del ordersInfo


def update():
    while True:
        if processingAlert == False:
            print(">>> update")
            for user in users:
                print("- update user " + user.email + " " + str(user.id))
                updateOrdersStatus(user)
        time.sleep(60 * 3)


def deleteBuyOrdersFromDb(user, exchangeId, tickerId, timeFrame, strategyId):
    if user.id in ordersData and exchangeId in ordersData[user.id]:
        for i in range(len(ordersData[user.id][exchangeId]) - 1, -1, -1):
            if ordersData[user.id][exchangeId][i]['ticker'] == tickerId and \
                    ordersData[user.id][exchangeId][i]['timeFrame'] == timeFrame and \
                    ordersData[user.id][exchangeId][i]['strategy'] == strategyId:
                del ordersData[user.id][exchangeId][i]

        saveOrdersData()


def handleSell(user, exchangeId, tickerId, timeFrame, strategyId):
    deleteBuyOrdersFromDb(user, exchangeId, tickerId, timeFrame, strategyId)


def getNumberSystemsForStrategy(user, exchangeId, strategyId):
    count = 0
    if user.id in ordersData and exchangeId in ordersData[user.id]:
        for ordersInfo in ordersData[user.id][exchangeId]:
            if ordersInfo['strategy'] == strategyId:
                count += 1

    return count


# Create Flask object called app.
app = Flask(__name__)

#os.environ['http_proxy'] = os.environ.get('FIXIE_URL', '')
#os.environ['https_proxy'] = os.environ.get('FIXIE_URL', '')

loadConfig()
loadOrdersData()
loadUsers()
for user in users:
    updateOrdersStatus(user)

# handleBuy(users[0], "TICK", "KUCOIN2", "1", "Yoyo", "SYM", "oooo", 10, 20)
# saveOrdersData()
# handleSell(users[0], "KUCOIN2", "TICK", "1", "Yoyo")
# saveOrdersData()


# sendOrder('Defense!, KUCOIN:compusdt, 0')
# sendOrder('DefenseSellLot3, KUCOIN:FORESTPLUSUSDT, 0')
# sendOrder('Buy, KUCOIN:compusdt, 1111')
# sendOrder('Sell, KUCOIN:compusdt, 0.01')
# sendOrder('Sell, KUCOIN:FORESTPLUSUSDT, 0.0578941')

# sendOrder('Buy, KUCOIN:buyusdt, 0.0405')
# sendOrder('Sell, KUCOIN:buyusdt, 0.0406')
# sendOrder('SellDefense, KUCOIN:buyusdt, 0.01')
# sendOrder('Buy, KUCOIN:CHRUSDT, 0.3996')
# sendOrder('Sell, KUCOIN:MATICUSDT, 1.489')
# sendOrder(users[0], 'Buy, KUCOIN:HAIUSDT, 0.0004')
# sendOrder(users[0], 'Buy, BINANCE:SXPUSDTPERP, 3.5, 1')
# sendOrder(users[0], 'Sell, BINANCE:SXPUSDTPERP, 3.5, 1')
# sendOrder(users[0], 'Buy, CAPITALCOM:AAPL, 152.4,1')
# sendOrder(users[0], 'Buy, CAPITALCOM:AAPL, 152.4,1')
# sendOrder(users[0], 'DefenseSellLot4, CAPITALCOM:DE30, 152.4,1')
# sendOrder(users[0], 'Buy, KUCOIN:HAIUSDT, 999999')
# sendOrder(users[0], 'DefenseSellLot4, KUCOIN:CIRUSUSDT, 999999, 3')

t = threading.Thread(target=update)
t.start()


@app.route("/")
def dashboard():
    orders = []

    return render_template('dashboard.html', orders=orders)

@app.route('/webhook', methods=['POST'])
def webhook():
    if request.method == 'POST':
        print(">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>")
        d = request.get_data(as_text=True)
        if d == "test":
            print("hello")
            return '', 200
        
        processingAlert = True
        for user in users:
            print("- user " + user.email + " " + str(user.id))
            sendOrder(user, d)
        processingAlert = False
        
        return '', 200
    else:
        abort(400)


if __name__ == '__main__':
    app.run()
