import os
from pypdf import PdfReader


def extract_every_single_image(pdf_path):
    output_dir = "all_extracted_images"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    reader = PdfReader(pdf_path)
    total_images = 0

    print(f"Rozpoczynam ekstrakcję z pliku: {pdf_path}")

    for i, page in enumerate(reader.pages):
        page_num = i + 1
        # Sprawdzanie zasobów strony
        if "/Resources" in page and "/XObject" in page["/Resources"]:
            xObject = page["/Resources"]["/XObject"].get_object()

            for obj in xObject:
                if xObject[obj]["/Subtype"] == "/Image":
                    total_images += 1
                    try:
                        image = xObject[obj]
                        data = image.get_data()

                        # Próba ustalenia rozszerzenia
                        ext = "png"
                        if "/Filter" in image:
                            if image["/Filter"] == "/DCTDecode":
                                ext = "jpg"
                            elif image["/Filter"] == "/JPXDecode":
                                ext = "jp2"

                        # Nazwa pliku: strona_nazwaObiektu.rozszerzenie
                        filename = f"page_{page_num}_{obj[1:]}.{ext}"
                        filepath = os.path.join(output_dir, filename)

                        with open(filepath, "wb") as f:
                            f.write(data)

                        print(f"Zapisano: {filename} ({len(data)} bytes)")
                    except Exception as e:
                        print(f"Błąd przy page {page_num}, obj {obj}: {e}")

    print(f"\nGotowe! Wyciągnięto łącznie {total_images} obrazów.")
    print(f"Znajdziesz je w folderze: {os.path.abspath(output_dir)}")


if __name__ == "__main__":
    extract_every_single_image(
        "./data/Koparkoladowarki-Klasa-III_PYTANIA-I-ZADANIA-1.pdf"
    )
