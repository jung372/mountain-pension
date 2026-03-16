
import pandas as pd

try:
    df = pd.read_excel(r'd:\05 AI 스터디\Sanji pension\KIKcd_B.20260301.xlsx')
    print("Columns structure:")
    for i, col in enumerate(df.columns):
        print(f"Index {i}: {col}")
    print("\nFirst row values:")
    print(df.iloc[0].to_dict())
    print("\nRow 2 values (usually has sigungu):")
    print(df.iloc[1].to_dict())
    print("\nRow 3 values (usually has eupmyeondong):")
    print(df.iloc[2].to_dict())
except Exception as e:
    print(f"Error: {e}")
