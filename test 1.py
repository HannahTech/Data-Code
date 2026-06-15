'''
TDA: احتمالاً مربوط به ساختمان‌های بخش Administrative (اداری).

TDC: مربوط به Corporating یا Canada Retail.

TDG: مربوط به گروه‌های خاص یا ساختمان‌های منطقه‌ای دیگر.
'''

import os
import pandas as pd

# ۱. آدرس پوشه فایل‌های اکسل خود را اینجا وارد کنید
folder_path = r"C:\path\to\your\downloaded\files"

# ۲. دیکشنری برای گروه‌بندی فایل‌ها بر اساس ۳ حرف اول
file_groups = {}

# اسکن پوشه و گروه‌بندی فایل‌ها
for file_name in os.listdir(folder_path):
    if file_name.endswith('.xlsx') or file_name.endswith('.xls') or file_name.endswith('.csv'):
        # گرفتن ۳ حرف اول نام فایل به صورت حروف بزرگ
        prefix = file_name[:3].upper()
        
        if prefix not in file_groups:
            file_groups[prefix] = []
        file_groups[prefix].append(file_name)

# ۳. تحلیل نقاط مشترک در هر گروه
analysis_results = []

print("--- آغاز تحلیل فایل‌های هم‌خانواده TD ---")

for prefix, files in file_groups.items():
    # اگر در یک گروه فقط یک فایل باشد، نیازی به پیدا کردن نقطه مشترک با فایل دیگر نیست
    if len(files) < 2:
        continue
        
    print(f"\nدر حال بررسی گروه: {prefix} (شامل {len(files)} فایل)...")
    
    # ذخیره ستون‌های هر فایل در این گروه برای مقایسه
    group_columns_dict = {}
    
    for file_name in files:
        file_path = os.path.join(folder_path, file_name)
        try:
            if file_name.endswith('.csv'):
                df = pd.read_csv(file_path, nrows=1)
            else:
                df = pd.read_excel(file_path, nrows=1)
            
            # ذخیره لیست ستون‌های فایل
            group_columns_dict[file_name] = set(df.columns)
        except Exception as e:
            print(f"خطا در خواندن فایل {file_name}: {e}")

    if not group_columns_dict:
        continue

    # پیدا کردن اشتراک (Intersection) ستون‌ها بین تمام فایل‌های این گروه
    common_columns = set.intersection(*group_columns_dict.values())
    
    # ذخیره نتایج تحلیل
    for file_name in files:
        analysis_results.append({
            "Prefix Group": prefix,
            "File Name": file_name,
            "Total Columns In File": len(group_columns_dict.get(file_name, [])),
            "Shared Columns In This Group": ", ".join(common_columns) if common_columns else "هیچ ستون مشترکی یافت نشد"
        })

# ۴. تبدیل نتیجه به فایل اکسل گزارش برای ارائه به مدیر ارشد
if analysis_results:
    df_report = pd.DataFrame(analysis_results)
    output_path = os.path.join(folder_path, "TD_Prefix_Common_Data_Report.xlsx")
    df_report.to_excel(output_path, index=False)
    print(f"\n[موفقیت] گزارش تحلیل ارتباط فایل‌ها با موفقیت در آدرس زیر ذخیره شد:\n{output_path}")
else:
    print("\nفایل‌های هم‌خانواده کافی (با پیشوند مشترک) برای مقایسه پیدا نشد.")
