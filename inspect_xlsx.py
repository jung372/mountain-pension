
import pandas as pd

try:
    df = pd.read_excel(r'd:\05 AI 스터디\Sanji pension\KIKcd_B.20260301.xlsx')
    print("Columns:", df.columns.tolist())
    print("First 5 rows:")
    print(df.head())
except Exception as e:
    print(f"Error: {e}")
