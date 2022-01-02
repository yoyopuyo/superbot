import gspread

class GSheet:
    def __init__(self, key):
        self.gc = gspread.service_account(filename='data/gsheet.json')
        self.spreadsheet = self.gc.open_by_key(key)
        self.sheets = {}
        
    def getSheetOrCreate(self, name):
        try:
            self.sheets[name] = self.spreadsheet.worksheet(name)
        except gspread.WorksheetNotFound:
            self.sheets[name] = self.spreadsheet.add_worksheet(title=name, rows="10", cols="10", index=0)    
        
    def addRow(self, sheetname, values):
        self.sheets[sheetname].append_rows(values=values)
