import json
import csv
from pathlib import Path
from typing import List

class FileUtils:
	def saveJsonToFile(fileName, data):
		with open(fileName, 'w') as outfile:
			json.dump(data, outfile)

	def loadJsonFromFile(fileName):
		file = Path(fileName)
		if file.is_file() == False:
			return {}

		with open(fileName) as json_file:
			data = json.load(json_file)
		return data

