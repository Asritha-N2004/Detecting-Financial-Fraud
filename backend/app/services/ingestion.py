from io import BytesIO
import json
import zipfile
import pandas as pd
from app.schemas.domain import Statement, Price


def parse_upload(content: bytes, filename: str, kind: str) -> list[dict]:
    extension = filename.rsplit('.',1)[-1].lower()
    if extension == 'json':
        rows = json.loads(content)
        if not isinstance(rows,list):
            raise ValueError('JSON upload must be an array of records')
    elif extension in {'csv','xlsx'}:
        if extension == 'xlsx':
            with zipfile.ZipFile(BytesIO(content)) as archive:
                if len(archive.infolist())>2000 or sum(i.file_size for i in archive.infolist())>20_000_000:
                    raise ValueError('Expanded workbook exceeds limits')
        frame = pd.read_csv(BytesIO(content)) if extension=='csv' else pd.read_excel(BytesIO(content),engine='openpyxl')
        rows = frame.astype(object).where(pd.notnull(frame),None).to_dict(orient='records')
    else:
        raise ValueError('Allowed formats: CSV, XLSX, JSON')
    if len(rows)>10000:
        raise ValueError('Too many rows')
    cls = Statement if kind=='financial-statements' else Price
    return [cls.model_validate(row).model_dump(mode='json') for row in rows]
