# pip install pandas openpyxl

import os
import pandas as pd

# ۱. آدرس پوشه‌ای که فایلهای اکسل دانلود شده در آن قرار دارند را اینجا بنویسید
folder_path = r"C:\path\to\your\downloaded\files"  # آدرس پوشه خود را جایگزین کنید

# ۲. ایجاد یک لیست خالی برای جمع‌آوری اطلاعات نهایی
data_map_list = []

# ۳. چرخیدن در میان تمام فایلهای پوشه
for file_name in os.listdir(folder_path):
    # فقط فایلهای اکسل بررسی شوند
    if file_name.endswith('.xlsx') or file_name.endswith('.xls') or file_name.endswith('.csv'):
        file_path = os.path.join(folder_path, file_name)
        
        try:
            # خواندن فایل بر اساس پسوند آن
            if file_name.endswith('.csv'):
                df = pd.read_csv(file_path, nrows=1)  # فقط ردیف اول برای سرعت بالا خوانده شود
            else:
                df = pd.read_excel(file_path, nrows=1)
            
            # استخراج نام ستون‌ها و نمونه داتا
            for column in df.columns:
                # گرفتن نمونه داتا (اگر ردیفی وجود داشت)
                sample_value = df[column].iloc[0] if not df.empty else "فایل خالی است"
                
                # اضافه کردن اطلاعات به لیست
                data_map_list.append({
                    "File Name": file_name,
                    "Column Name": column,
                    "Sample Data": sample_value
                })
                
        except Exception as e:
            print(f"خطا در خواندن فایل {file_name}: {e}")

# ۴. تبدیل لیست نهایی به یک دیتافریم پانداس
df_final_map = pd.DataFrame(data_map_list)

# ۵. ذخیره کردن دیتامپ نهایی در یک فایل اکسل جدید
output_file = os.path.join(folder_path, "TD_BIM_Data_Map_Report.xlsx")
df_final_map.to_excel(output_file, index=False)

print(f"عملیات با موفقیت انجام شد! فایل دیتامپ شما در این آدرس ذخیره شد:\n{output_file}")




'''
این فایل اکسل خروجی (Data Map) چه شکلی خواهد بود؟خروجی این پایتون یک جدول ۳ ستونه منظم در فایل TD_BIM_Data_Map_Report.xlsx خواهد بود که ساختاری شبیه به این دارد:File NameColumn NameSample DataNew_Location_IDs.xlsxBuilding_IDTDC0001New_Location_IDs.xlsxFloor_NameFloor 02Teknion_Furniture.xlsxManufacturer_CodeTEK-CH-09our_excel_1.xlsxTD_Type_IDTD_MO_WA_EX_CU_001

'''


