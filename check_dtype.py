
import pandas as pd

try:
    df = pd.read_excel(r'd:\05 AI 스터디\Sanji pension\KIKcd_B.20260301.xlsx')
    first_col = df.iloc[:, 0]
    print(f"Data type: {first_col.dtype}")
    print(f"First 5 values: {first_col.head().tolist()}")
except Exception as e:
    print(f"Error: {e}")
