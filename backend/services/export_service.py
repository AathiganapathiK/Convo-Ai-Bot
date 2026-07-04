from openpyxl import Workbook
from io import BytesIO


def create_excel_report(
    question,
    summary,
    data
):

    workbook = Workbook()

    # Sheet 1
    sheet1 = workbook.active
    sheet1.title = "Analytics Data"

    if data:

        headers = list(data[0].keys())

        sheet1.append(headers)

        for row in data:
            sheet1.append(list(row.values()))

    # Sheet 2
    sheet2 = workbook.create_sheet(
        title="Business Summary"
    )

    sheet2["A1"] = "Question"
    sheet2["B1"] = question

    sheet2["A3"] = "Summary"
    sheet2["B3"] = summary

    excel_file = BytesIO()

    workbook.save(excel_file)

    excel_file.seek(0)

    return excel_file