
import pandas as pd

try:
    df = pd.read_excel(r'd:\05 AI 스터디\Sanji pension\KIKcd_B.20260301.xlsx')
    # Filter for Gangwon
    gangwon = df[df.iloc[:, 1].str.contains('강원', na=False)]
    print(gangwon.head(10))
except Exception as e:
    print(f"Error: {e}")
