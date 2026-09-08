import win32com.client
import os

docx_path = os.path.abspath(r'C:\Users\olomu\Downloads\fyp\uploads\Chapter_4_Results_and_Discussion.docx')
try:
    word = win32com.client.Dispatch('Word.Application')
    word.Visible = False
    doc = word.Documents.Open(docx_path)
    pages = doc.ComputeStatistics(2)  # 2 = wdStatisticPages
    words = doc.ComputeStatistics(0)  # 0 = wdStatisticWords
    paras = doc.ComputeStatistics(1)  # 1 = wdStatisticParagraphs
    chars = doc.ComputeStatistics(3)  # 3 = wdStatisticCharacters
    doc.Close(False)
    word.Quit()
    print(f"PAGES: {pages}")
    print(f"WORDS: {words}")
    print(f"PARAGRAPHS: {paras}")
    print(f"CHARACTERS: {chars}")
except Exception as e:
    print(f"Error: {e}")
