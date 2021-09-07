import boto3
import json
import os

class S3FileUtils:
    def __init__(self):
        self.session = boto3.session.Session()
        self.s3 = self.session.client(service_name='s3', aws_access_key_id=os.getenv('s3-key'), aws_secret_access_key=os.getenv('s3-secret'))
        
    def saveJsonToFile(self, fileName, data):
        obj = self.s3.put_object(Body=str(json.dumps(data)), Bucket=os.getenv('s3-bucket'),Key=fileName)

    def loadJsonFromFile(self, fileName):
        result = self.s3.get_object(Bucket=os.getenv('s3-bucket'), Key=fileName)
        str = result["Body"].read().decode()
        return json.loads(str)

