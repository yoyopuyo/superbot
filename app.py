#docker logs tradingviewbot_web_1
import time
import threading
import os

from fileutils import FileUtils
from flask import Flask, request, abort, render_template
from mail import Mail
from userSimple import UserSimple
from s3FileUtils import S3FileUtils
from gsheet import GSheet
import datetime

ordersDataFileName = 'data/ordersData.txt'
configFileName = 'data/config.txt'

processingAlert = False

config = {}
users = []
ordersData = []

saveToS3 = False
initS3 = False
loadUsersFromEnv = False

#if os.getenv('save-to-s3', None) == "1":
#    print("Load orders from s3")
#    saveToS3 = True
#    initS3 = True

configFromS3 = False
#if os.getenv('config-from-s3', None) == "1":
#    print("Load config from s3")
#    configFromS3 = True
#    initS3

if initS3:
    s3 = S3FileUtils()
    
def getSymbolRightPart(symbol):
    if '/' in symbol:
        return symbol.split('/')[1]

    return None

def loadConfig():
    print("----------- loadConfig")
    global config
    global configFromS3

    if saveToS3:
        config = s3.loadJsonFromFile('config.txt')
    else:    
        config = FileUtils.loadJsonFromFile(configFileName)

def loadUsers():
    global users
    users = []
    if loadUsersFromEnv:
        for i in range(1, 3):
            mail = os.getenv(str(i) + "-mail")
            if mail is not None:
                print(mail)
                user = UserSimple()
                user.id = str(i)
                user.email = mail
                
                for exchangeId in config["exchanges"]:
                    print("Try to create exchange " + exchangeId)
                    if user.hasExchange(exchangeId) == False:
                        key = os.getenv(str(i) + "-" + exchangeId + "-key")
                        if key is not None:
                            secret = os.getenv(str(i) + "-" + exchangeId + "-secret")
                            password = os.getenv(str(i) + "-" + exchangeId + "-password")
                            user.addExchange(exchangeId, key, secret, password)
                        
                user.print()
                users.append(user)
    else:        
        for userData in config['users']:
            user = UserSimple(userData)
            users.append(user)


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
    #print("save orders " + str(saveToS3))
    
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

def getPriceOffset(exchangeId, symbol, alertId):
    return getAlertValue(exchangeId, symbol, alertId, "priceOffset", 0)

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

    return default

def getConfigAmountToBuy(user, exchangeId, symbol, numBuyOrders, ordersInfo):
    amountToBuy = 0
    amountFirstBuyPercentOfBalance = getConfigValue(exchangeId, symbol, "amountFirstBuyPercentOfBalance", 0)

    if amountFirstBuyPercentOfBalance != 0:
        print("amountFirstBuyPercentOfBalance " + str(amountFirstBuyPercentOfBalance))
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
        print("amount " + str(amount))
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
        if symbol.startswith("USD"):
            symbol = symbol + '/USD'

        if 'USD' not in symbol:
            symbol = symbol + 'USD'

    if 'PERP' in symbol:
        symbol = symbol.replace("PERP", "")
        if exchangeId == "BINANCE":
            exchangeId = "BINANCEUSDM"
        if exchangeId == "FTX":
            symbol = symbol + "/USDT"
            
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
        if not symbol.startswith('USD'):
            symbol = symbol.replace("USD", "/USD")
        symbol = symbol.replace("USDC", "/USDC")
        symbol = symbol.replace("BUSD", "/BUSD")
        symbol = symbol.replace("//", "/")

    price = float(info[2])
    if len(info) > 3:
        timeFrame = info[3]
    else:
        timeFrame = '?'

    if exchangeId == "BINANCEUSDM":
        leverage = getAlertValue(exchangeId, symbol, alertId, "leverage", 20)
        user.getExchange('binanceusdm').setLeverage(symbol, leverage)
        user.getExchange('binanceusdm').setDualPositionMode()
        print("set leverage " + str(leverage))
    if exchangeId == "FTX":
        leverage = getAlertValue(exchangeId, symbol, alertId, "leverage", 20)
        exchange.setLeverage(symbol, leverage)
        print("set leverage " + str(leverage))

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

    if action == 'setTP':
        if getAlertValue(exchangeId, symbol, alertId, "type", "") == 'breakeven':
            ordersInfo = getOrderData(user, exchangeId, tickerId, timeFrame, strategyId)
            if ordersInfo == None:
                print('No buy order found for ' + tickerId)
                return
            
            for order in ordersInfo['orders']:
                if order['status'] == 'open' or order['status'] == '?':
                    exchange.createStoploss(symbol, order['orderId'], "", float(order['amountSpent']), float(order['price']), float(order['price']), 1)            
            
            handleSell(user, exchangeId, tickerId, timeFrame, strategyId)
            if config['options']['sendMail'] and getSendMail(exchangeId, symbol, alertId):
                Mail.sendMail(action + ': sold ' + symbol + ', setTp breakeven', '', user.email)                            
        return 
    
    side = ''
    actionType = ''
    shorting = False
    
    if action == 'buy':
        side = 'buy'
        actionType = 'open'

    if action == 'short':
        side = 'sell'
        actionType = 'open'

    if action == 'sellAll' or action == 'sellBreakEven' or action == 'sellLadder':
        side = 'sell'
        actionType = 'close'

    if action == 'closeShortAll' or action == 'closeShortBreakEven':
        side = 'buy'
        actionType = 'close'
        shorting = True
        
    if action == 'sellOneOrder':
        side = 'sell'
        actionType = 'closeOneOrder'

    if action == 'closeShortOneOrder':
        side = 'buy'
        actionType = 'closeOneOrder'
        shorting = True

    if action == 'setStopLossAllBuys':
        actionType = 'setStopLossAllBuys'
        
    if actionType == '':
        return

    orderType = getOrderType(exchangeId, symbol, alertId)
    print(symbol)

    if actionType == 'open':
        numBuyOrders = getNumberBuyOrders(user, exchangeId, tickerId, timeFrame, strategyId)
        if numBuyOrders == 0:
            maxSystems = getConfigValue(exchangeId, symbol, "maxSystems", 9999999)
            numberSystems = getNumberSystemsForExchange(user, exchangeId)
            print("systems: " + str(numberSystems) + "/" + str(maxSystems))
            if numberSystems >= maxSystems:
                print("Too many systems for exchange")
                return

            maxSystems = getAlertValue(exchangeId, symbol, alertId, "maxSystems", 9999999)
            if getNumberSystemsForStrategy(user, exchangeId, strategyId) >= maxSystems:
                print("Too many systems for strategy")
                return

            minBalanceForFirstPurchaseFreePercentOfTotal = getConfigValue(exchangeId, symbol, "minBalanceForFirstPurchaseFreePercentOfTotal", 0)
            print("minBalanceForFirstPurchaseFreePercentOfTotal " + str(minBalanceForFirstPurchaseFreePercentOfTotal))
            freeBalance = getCachedBalance(user, exchangeId, symbol)
            total = getCachedBalance(user, exchangeId, symbol, 'total')
            print("Free Balance " + str(freeBalance) + " total Balance " + str(total) + " minBalanceForFirstPurchaseFreePercentOfTotal " + str(minBalanceForFirstPurchaseFreePercentOfTotal))
            if minBalanceForFirstPurchaseFreePercentOfTotal != 0 and (1 - (total - freeBalance) / total) * 100 < minBalanceForFirstPurchaseFreePercentOfTotal:
                print("Not enough funds minBalanceForFirstPurchaseFreePercentOfTotal")
                return
    
            minBalanceForFirstPurchase = getConfigValue(exchangeId, symbol, "minBalanceForFirstPurchase", 0)
            print("minBalanceForFirstPurchase " + str(minBalanceForFirstPurchase))
            freeBalance = getCachedBalance(user, exchangeId, symbol)
            if minBalanceForFirstPurchase != 0 and freeBalance < minBalanceForFirstPurchase:
                print("Not enough funds minBalanceForFirstPurchase")
                return

        ordersInfo = getOrderData(user, exchangeId, tickerId, timeFrame, strategyId)
        amountToBuy = getConfigAmountToBuy(user, exchangeId, symbol, numBuyOrders, ordersInfo)

        priceOffset = getPriceOffset(exchangeId, symbol, alertId)
        if priceOffset != 0:
            if side == 'buy':
                price = price + price * priceOffset / 100
            else:
                price = price - price * priceOffset / 100
            print("Price after priceOffset " + str(price))
            
        if price == 0:
            return

        if amountToBuy == 0:
            print("Buy 0, return")
            return

        print("amountToBuy " + str(amountToBuy))

        amount = amountToBuy
        
        if side == 'buy':
            invertedSide = 'sell'            
            result = exchange.buy(symbol, orderType, amount, price, actionType)
        else:
            invertedSide = 'buy'                
            result = exchange.sell(symbol, orderType, amount, price, actionType)

        if result != None:
            orderId = exchange.getOrderIdFromResult(result)

            newOrder = handleBuy(user, tickerId, exchangeId, timeFrame, strategyId, symbol, orderId, price, amountToBuy)
            
            print("stoploss? " + str(getAlertValue(exchangeId, symbol, alertId, "stoploss", False)))
            if getAlertValue(exchangeId, symbol, alertId, "stoploss", False):
                stoplossPrice = 0.0
                maxStoplossPrice = 0.0
                stoplossStep = 0.0
                if side == 'buy':
                    if len(info) > 6:
                        stoplossPrice = result['average'] * (1 - float(info[4]))
                        maxStoplossPrice = result['average'] * (1 + float(info[5]))
                        stoplossStep = float(info[6])
                else:
                    if len(info) > 6:
                        stoplossPrice = result['average']  * (1 + float(info[4]))
                        maxStoplossPrice = result['average'] * (1 - float(info[5]))
                        stoplossStep = float(info[6])

                averagePrice = result['average']
                print("set stop loss at " + str(stoplossPrice) + ", average price " + str(averagePrice) + ", max stop loss " +str(maxStoplossPrice)+", step " + str(stoplossStep))
                
                if stoplossPrice > 0:
                    #amount = int(amount / price)
                    #if amount == 0:
                        #amount = float(amount / price)
                    #amount = amount * averagePrice
                    result = exchange.createStoploss(symbol, orderId, side, amount, stoplossPrice, averagePrice)
                    if result != None:
                        handleBuyStopLoss(newOrder, exchange.getOrderIdFromResult(result), side, stoplossPrice, maxStoplossPrice, stoplossStep, averagePrice, amount)
                
            error = ''
        else:
            error = ", error"

        if config['options']['sendMail'] and getSendMail(exchangeId, symbol, alertId):
            Mail.sendMail(action + ', bought ' + symbol + error + ", " + str(timeFrame) + ", Buy " + str(numBuyOrders + 1),
                          symbol + ' amountToBuy = ' + str(amount) + ', price = ' + str(price) + ', ' + orderType, user.email)    
    elif actionType == 'closeOneOrder':
        ordersInfo = getOrderData(user, exchangeId, tickerId, timeFrame, strategyId)
        if ordersInfo == None:
            print('No buy order found for ' + tickerId)
            return

        numberCoinsBought, totalSpent, breakEvenPrice = getOrdersInfo(exchange, ordersInfo)

        if price == 0:
            return

        if numberCoinsBought <= 0:
            print('No coins to sell for ' + tickerId)
            return

        numBuyOrders = getNumberBuyOrders(user, exchangeId, tickerId, timeFrame, strategyId)
        toSell = numberCoinsBought / numBuyOrders

        totalToReceive = toSell * price
        
        if exchangeId == "CAPITALCOM":
            result = {}
        else:
            if side == 'buy':
                result = exchange.buy(symbol, orderType, toSell, price, actionType)
            else:
                result = exchange.sell(symbol, orderType, toSell, price, actionType)

        if result != None:
            deleteBuyOrdersFromDbAtIndex(user, exchangeId, tickerId, timeFrame, strategyId, 0)
            error = ''
        else:
            error = ", error"

        if config['options']['sendMail'] and getSendMail(exchangeId, symbol, alertId):
            Mail.sendMail(action + ': close order ' + symbol, '', user.email)
            
    elif actionType == 'close':
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

        priceOffset = getPriceOffset(exchangeId, symbol, alertId)
        if priceOffset != 0:
            if side == 'buy':
                price = price + price * priceOffset / 100
            else:
                price = price - price * priceOffset / 100
            print("Price after priceOffset " + str(price))

        if price == 0:
            return

        if numberCoinsBought <= 0:
            print('No coins to sell for ' + tickerId)
            return

        if quantityPercent == 100 and keepFreeCoins:
            toSell = numberCoinsBought * quantityPercent / 100
        else:
            toSell = numberCoinsBought * quantityPercent / 100

        if exchangeId == "CAPITALCOM":
            result = {}
        else:
            if side == 'buy':
                result = exchange.buy(symbol, orderType, toSell, price, actionType)
            else:
                result = exchange.sell(symbol, orderType, toSell, price, actionType)
                
        if result != None:
            if result['average'] != None:
                totalToReceive = toSell * result['average']
            else:
                totalToReceive = toSell * price
            handleSell(user, exchangeId, tickerId, timeFrame, strategyId)
            error = ''
        else:
            error = ", error"
            totalToReceive = toSell * price

        gainPercent = (totalToReceive - totalSpent) / totalSpent
        if shorting:
            gainPercent = -gainPercent

        if gainPercent >= 0:
            gainPercentStr = "+{:.2%}".format(gainPercent)
        else:
            gainPercentStr = "{:.2%}".format(gainPercent)

        gsheet.getSheetOrCreate(exchangeId)
        if shorting:
            moneyIn = totalToReceive
            moneyOut = totalSpent
            moneyGained = -(totalToReceive - totalSpent)
        else:
            moneyIn = totalSpent
            moneyOut = totalToReceive
            moneyGained = totalToReceive - totalSpent

        if exchangeId != "CAPITALCOM":
            gsheet.addRow(exchangeId, [[datetime.datetime.now().strftime('%Y-%m-%d'), symbol, strategyId, moneyIn, moneyOut, gainPercentStr, moneyGained]])

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
            exchange.cancelOrder(order['orderId'], ordersInfo['symbol'])
        if 'stoploss' in order and order['stoploss']['orderId'] != None:
            exchange.cancelOrder(order['stoploss']['orderId'], ordersInfo['symbol'])


def getOrdersInfo(exchange, ordersInfo):
    coins = 0
    totalSpent = 0
    breakEvenPrice = 99999999
    #pricesOfOrders = []
    #coinsOfOrders = []
    
    
    for order in ordersInfo['orders']:
        realOrder = exchange.getOrderById(order['orderId'], ordersInfo['symbol'])
        if realOrder == None:
            print("BuyOrder for " + ordersInfo['ticker'] + " with id " + str(order['orderId']) + " not found.")
        else:
            coins += realOrder['filled']
            totalSpent += (realOrder['filled'] * realOrder['price'])
            #coinsOfOrders.append(realOrder['filled'])
            #pricesOfOrders.append(realOrder['filled'])

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

    newOrder = {'orderId': orderId, 'status': 'open', 'time': 0, 'price': str(price), 'amountSpent': str(amountToBuy)}
    
    if exchangeId == 'ftx':
        newOrder['status'] = 'closed'
        
    o['orders'].append(newOrder)

    saveOrdersData()
    return newOrder

def handleBuyStopLoss(order, orderId, side, stopLossPrice, maxStoplossPrice, stoplossStep, buyPrice, amount):
    order['stoploss'] = {'orderId': orderId, 'side': side, 'currentStopLossPrice': stopLossPrice, 'originalStopLossPrice': stopLossPrice, 'maxStoplossPrice': maxStoplossPrice, 'stoplossStep': stoplossStep, 'buyPrice': buyPrice, 'isTrailing': True, 'amount': amount }
    
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

                if order['status'] != 'stoplossed' and 'stoploss' in order:
                    stoploss = order['stoploss']
                    stoplossOrder = user.getExchange(exchangeId).getOrderById(stoploss['orderId'], ordersInfo['symbol'])
                    if stoplossOrder == None:
                        print("stop loss order not found, " + " order " + order['status'])
                    else:
                        print ("========================== stop loss order " + stoplossOrder['status'] + " order " + order['status'])
                        if stoplossOrder['status'] == 'closed':
                            order['status'] = 'stoplossed'
                            stoploss['orderId'] = None
                            changed = True
                        if stoploss['isTrailing']:
                            print(stoploss)
                            ticker = user.getExchange(exchangeId).getTicker(ordersInfo['symbol'])
                            if ticker != None:
                                print(ticker)
                                side = stoploss['side']
                                buyPrice = stoploss['buyPrice']
                                maxStoplossPrice = stoploss['maxStoplossPrice']
                                currentStopLossPrice = stoploss['currentStopLossPrice']
                                gain = (ticker['last'] - buyPrice) / buyPrice / 2
                                print('gain ' + str(gain))                                
                                if (side == 'buy' and gain > 0) or (side == 'sell' and gain < 0):
                                    newStoplossPrice = stoploss['originalStopLossPrice'] * (1 + gain)
                                    print('newStoplossPrice ' + str(newStoplossPrice))
                                    isTrailing = True
                                    if (side == 'buy' and newStoplossPrice > maxStoplossPrice) or (side == 'sell' and newStoplossPrice < maxStoplossPrice):
                                        newStoplossPrice = maxStoplossPrice
                                        isTrailing = False
                                        print("reached max stoploss")
                                    if (side == 'buy' and newStoplossPrice > currentStopLossPrice) or (side == 'sell' and newStoplossPrice < currentStopLossPrice):
                                        gainFromLastStop = (currentStopLossPrice - newStoplossPrice) / currentStopLossPrice
                                        print('gainFromLastStop ' + str(gainFromLastStop))
                                        if (side == 'buy' and -gainFromLastStop > 0.005) or (side == 'sell' and gainFromLastStop > 0.005):
                                            amount = stoploss['amount']
                                            result = user.getExchange(exchangeId).moveStoploss(order['orderId'], stoploss['orderId'], ordersInfo['symbol'], side, amount, newStoplossPrice, buyPrice)
                                            if result != None:
                                                stoploss['orderId'] = user.getExchange(exchangeId).getOrderIdFromResult(result)
                                                stoploss['currentStopLossPrice'] = newStoplossPrice
                                                stoploss['isTrailing'] = isTrailing
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
            #print(">>> update")
            for user in users:
                #print("- update user " + user.email + " " + str(user.id))
                updateOrdersStatus(user)
        time.sleep(60)

def deleteBuyOrdersFromDbAtIndex(user, exchangeId, tickerId, timeFrame, strategyId, deleteAtIndex):
    print("deleteBuyOrdersFromDbAtIndex")
    if user.id in ordersData and exchangeId in ordersData[user.id]:
        for i in range(len(ordersData[user.id][exchangeId]) - 1, -1, -1):
            if ordersData[user.id][exchangeId][i]['ticker'] == tickerId and \
                    ordersData[user.id][exchangeId][i]['timeFrame'] == timeFrame and \
                    ordersData[user.id][exchangeId][i]['strategy'] == strategyId:
                del ordersData[user.id][exchangeId][i]['orders'][deleteAtIndex]

        saveOrdersData()

def deleteBuyOrdersFromDb(user, exchangeId, tickerId, timeFrame, strategyId):
    print("deleteBuyOrdersFromDb")
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

def getNumberSystemsForExchange(user, exchangeId):
    count = 0
    if user.id in ordersData and exchangeId in ordersData[user.id]:
        for ordersInfo in ordersData[user.id][exchangeId]:
            count += 1

    return count


# Create Flask object called app.
app = Flask(__name__)

#os.environ['http_proxy'] = os.environ.get('FIXIE_URL', '')
#os.environ['https_proxy'] = os.environ.get('FIXIE_URL', '')

loadConfig()
loadOrdersData()
loadUsers()

#s = 'SXP/USDT'
#users[0].getExchange('binanceusdm').setLeverage(s, 2)
#try:
#    users[0].getExchange('binanceusdm').setMarginType(s, "ISOLATED")
#except:
#    print("ee")
#users[0].getExchange('binanceusdm').buy(s, 'limit', 3, 2.6210 )
#users[0].getExchange('binanceusdm').sell(s, 'limit', 3 * 3, 2.6255 )

#exit()

#users[0].getExchange('naga').createStoploss('XAGUSD', 23453803, "", 100, 0, 0, 1)

gsheet = GSheet('1W9nP71CdX7MH0Qmv6fqEipOvONdkWResgQjVKnxocJ4')

print("Ready to roll")

for user in users:
    updateOrdersStatus(user)

print("orderStatus updated")

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
#sendOrder(users[0], 'Short, CAPITALCOM:EURGBPe, 999999, 1')
#sendOrder(users[0], 'Buy, BINANCE:COTIUSDTPERP, 0.474, 5')
#sendOrder(users[0], 'Short, BINANCE:OMGUSDTPERP, 1.475, 5')
#sendOrder(users[0], 'Cover, BINANCE:COTIUSDTPERP, 0.4755, 5')

#sendOrder(users[0], 'Buy, CAPITALCOM:XAGUSD, 0.309,S,0.01,0.01,0.005')
#sendOrder(users[0], 'SellBreakeven, CAPITALCOM:XAGUSD, 0.309,S,0.01,0.01,0.005')
#sendOrder(users[0], 'Buy, FTX:SRNPERP, 0.007225, 5')
#time.sleep(120)
#sendOrder(users[0], 'Sell, FTX:SRNPERP, 0.474, 5')

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
        print(d)
        if d == "test":
            print("hello")
            return '', 200
        elif d == "cfg":
            print("cfg")
            loadConfig()
            return '', 200
        elif d == "orders":
            print("orders")
            loadOrdersData()
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
    app.run(host='0.0.0.0', debug=True)
