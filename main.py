import json
import re
import os
import hashlib
from pypdf import PdfReader


def clean_text(text):
    if not text:
        return ""
    # Usuwanie stopek, nagłówków i zbędnych kodów technicznych
    text = re.sub(r"Strona \d+ z \d+CEO/\d{4}/\d+\.\d+", "", text)
    text = text.replace("Koparkoładowarki Klasa III", "")
    return " ".join(text.split()).strip()


def extract_quiz_complete(quiz_pdf_path, answers_pdf_path):
    image_dir = "extracted_images"
    if not os.path.exists(image_dir):
        os.makedirs(image_dir)

    reader = PdfReader(quiz_pdf_path)

    # 1. Pobieranie klucza odpowiedzi
    ans_text = "".join([p.extract_text() for p in PdfReader(answers_pdf_path).pages])
    answers_map = {
        num: ans.lower() for num, ans in re.findall(r"(\d+)\.\s+([A-C])", ans_text)
    }

    mc_questions = []
    maintenance_tasks = []
    technological_tasks = []

    last_valid_table_image = None
    current_section = "mc"  # mc, maintenance, tech

    image_keywords = [
        "rysunku",
        "tabeli",
        "symbol",
        "grafice",
        "piktogram",
        "poniżej",
        "przedstawiony",
        "tabelę",
        "odległość X",
        "odległości X",
    ]

    print("Rozpoczynam pełną ekstrakcję (Test + Zadania Otwarte)...")

    for i, page in enumerate(reader.pages):
        page_num = i + 1
        page_text = page.extract_text()

        # --- WYKRYWANIE SEKCJI ---
        if "Zadania obsługowe" in page_text:
            current_section = "maintenance"
        elif "Zadania technologiczne" in page_text:
            current_section = "tech"

        # --- KROK A: Pobieranie obrazów ze strony (Pomiń Image21) ---
        current_page_images = []
        if "/Resources" in page and "/XObject" in page["/Resources"]:
            xObj = page["/Resources"]["/XObject"].get_object()
            for obj_id in sorted(xObj.keys()):
                if xObj[obj_id]["/Subtype"] == "/Image":
                    if "Image21" in obj_id:
                        continue  # Omijamy logo

                    try:
                        data = xObj[obj_id].get_data()
                        ext = (
                            "jpg"
                            if xObj[obj_id].get("/Filter") == "/DCTDecode"
                            else "png"
                        )
                        fname = f"page_{page_num}_{obj_id[1:]}.{ext}"
                        with open(os.path.join(image_dir, fname), "wb") as f:
                            f.write(data)
                        current_page_images.append(fname)
                    except:
                        continue

        if current_page_images:
            last_valid_table_image = current_page_images[0]

        # --- KROK B: Parsowanie w zależności od sekcji ---

        if current_section == "mc":
            # Pytania wielokrotnego wyboru
            blocks = re.split(r"\n(?=\d{1,3}\.\n)", page_text)
            page_q_list = []
            for block in blocks:
                match = re.search(
                    r"^(\d{1,3})\.\n\s*(.+?)\s*a\)\s*(.+?)\s*b\)\s*(.+?)\s*c\)\s*(.+?)(?=\n\d{1,3}\.\n|$)",
                    block,
                    re.DOTALL,
                )
                if match:
                    needs_img = any(
                        kw in match.group(2).lower() for kw in image_keywords
                    )
                    page_q_list.append(
                        {
                            "id": match.group(1),
                            "needs_img": needs_img,
                            "match": match,
                            "text": match.group(2),
                        }
                    )

            # Logika dopasowania obrazu (Twoja strategia)
            q_needs_list = [q for q in page_q_list if q["needs_img"]]
            img_iter = iter(current_page_images)

            for q in page_q_list:
                assigned_img = None
                if q["needs_img"]:
                    if (
                        len(current_page_images) == len(q_needs_list)
                        and len(current_page_images) > 0
                    ):
                        assigned_img = next(img_iter)
                    elif len(current_page_images) == 1:
                        assigned_img = current_page_images[0]
                    elif len(current_page_images) == 0 and "tabel" in q["text"].lower():
                        assigned_img = last_valid_table_image
                    elif len(current_page_images) > 0:
                        assigned_img = next(img_iter, current_page_images[0])

                mc_questions.append(
                    {
                        "id": int(q["id"]),
                        "question": clean_text(q["match"].group(2)),
                        "options": {
                            "a": clean_text(q["match"].group(3)),
                            "b": clean_text(q["match"].group(4)),
                            "c": clean_text(q["match"].group(5)),
                        },
                        "correct_answer": answers_map.get(q["id"]),
                        "image": assigned_img,
                    }
                )

        else:
            # Zadania praktyczne (Otwarte)
            # Szukamy wzorca: Numer. [Nowa linia] Proszę...
            open_matches = re.findall(
                r"(\d+)\.\s*\n\s*(Proszę.*?)(?=\n\d+\.\s*\n|$)", page_text, re.DOTALL
            )

            # Policz zadania z obrazkami na stronie
            tasks_needing_img = [
                t
                for t in open_matches
                if any(kw in t[1].lower() for kw in image_keywords)
            ]
            img_iter = iter(current_page_images)

            for num, text in open_matches:
                needs_img = any(kw in text.lower() for kw in image_keywords)
                assigned_img = None

                if needs_img:
                    if (
                        len(current_page_images) == len(tasks_needing_img)
                        and len(current_page_images) > 0
                    ):
                        assigned_img = next(img_iter)
                    elif len(current_page_images) > 0:
                        assigned_img = current_page_images[0]
                    elif "tabel" in text.lower():
                        assigned_img = last_valid_table_image

                task_obj = {
                    "id": int(num),
                    "task": clean_text(text),
                    "image": assigned_img,
                }

                if current_section == "maintenance":
                    maintenance_tasks.append(task_obj)
                else:
                    technological_tasks.append(task_obj)

    # 3. Zapisywanie wszystkich plików
    def save_json(data, filename):
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

    save_json(mc_questions, "questions_test.json")
    save_json(maintenance_tasks, "tasks_maintenance.json")
    save_json(technological_tasks, "tasks_technological.json")

    print(f"Gotowe! Wygenerowano:")
    print(f"- {len(mc_questions)} pytań testowych")
    print(f"- {len(maintenance_tasks)} zadań obsługowych")
    print(f"- {len(technological_tasks)} zadań technologicznych")


if __name__ == "__main__":
    extract_quiz_complete(
        "./data/Ladowarki-jednonaczyniowe-Klasa-III_PYTANIA-I-ZADANIA-1.pdf",
        "./data/Ladowarki-jednonaczyniowe-Klasa-III_KLUCZ-ODPOWIEDZI-1.pdf",
    )
