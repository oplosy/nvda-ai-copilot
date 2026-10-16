# Proje: NVDA AI Copilot

## Amaç
NVDA kullanıcısına, erişilemeyen web öğelerinde AI ile yardım eden bir araç.
Siteyi düzeltmez; NVDA'yı değiştirmez. AI çıktısı her zaman "AI yorumu:" önekiyle ayrı kanaldan verilir.

## Mimari
- nvda-addon/   : NVDA GlobalPlugin. Kısayol, konuşma (ui.message), onay UX'i.
- coordinator/  : Yerel Python servis. Bağlam birleştirme, gizlilik filtresi, LLM çağrısı, aksiyon politikası.
- extension/    : Chrome MV3 eklentisi. DOM, ARIA, bounding box, ekran görüntüsü, aksiyon yürütme.
- İletişim: extension <-> coordinator = Chrome Native Messaging; nvda-addon <-> coordinator = localhost.

## Kurallar
- LLM sadece extension'ın verdiği element ID'lerinden seçer; koordinat üretmez.
- İzin verilen aksiyon tiplerini coordinator belirler, LLM değil.
- Her state değiştiren aksiyondan sonra DOM yeniden okunur.
- password, OTP, kart alanlarının değeri modele asla gönderilmez.
- AI, NVDA'nın normal gezinme yoluna senkron girmez; yalnızca kısayolla çağrılır.
- Şu an kapsam DIŞI: form gönderme, ödeme, otonom çok adımlı görev, CAPTCHA çözme.

## Test
- NVDA davranışını sen test edemezsin; kullanıcı manuel test eder ve NVDA logunu (NVDA+F1 / Log viewer) yapıştırır.
- coordinator ve extension mantığı için birim testleri yaz.

## Referans
docs/research.md arka plan içindir; kaynaklarında hatalar var, teknik kararlar için NVDA Developer Guide ve Chrome Extension docs esas alınır.