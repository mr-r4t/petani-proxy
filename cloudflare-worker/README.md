# Cloudflare Email Worker Inbox — PetaniProxy

Worker ini bertugas menerima email dari **Cloudflare Email Routing** (Catch-all), mem-parse isi pesan, dan menyimpannya di **Cloudflare Workers KV**. PetaniProxy akan memanggil endpoint `/inbox` untuk membaca link aktivasi / verifikasi akun Webshare.

---

## 🚀 Cara Setup Cepat (5 Menit)

### 1. Hubungkan Domain ke Cloudflare
1. Tambahkan domain Anda di Cloudflare Dashboard.
2. Buka menu **Email Routing** di domain tersebut, aktifkan Email Routing (pastikan DNS MX Cloudflare sudah terpasang).
3. Buat aturan **Catch-all**:
   - Match: *Catch-all* (semua alamat email).
   - Action: *Send to a Worker* (pilih nama Worker setelah di-deploy pada langkah di bawah).

### 2. Deploy Worker Ini
Buka terminal di folder `cloudflare-worker/`:
```bash
# 1. Masuk folder & install dependensi
npm install

# 2. Login ke akun Cloudflare jika belum
npx wrangler login

# 3. Buat KV Namespace untuk penampungan email
npx wrangler kv namespace create INBOX
```
Catat `id` namespace KV yang muncul di terminal, lalu buat file `wrangler.toml` (salin dari `wrangler.example.toml`):
```toml
name = "petani-proxy-inbox"
main = "worker.js"
compatibility_date = "2024-09-01"

[[kv_namespaces]]
binding = "INBOX"
id = "paste_id_kv_namespace_disini"
```

Set secret token untuk keamanan endpoint `/inbox`:
```bash
npx wrangler secret put WORKER_SECRET
# Masukkan kata sandi rahasia Anda, misal: TokenRahasiaBansos123
```

Deploy ke Cloudflare:
```bash
npx wrangler deploy
```
Setelah deploy selesai, catat URL Worker Anda, misalnya:  
`https://petani-proxy-inbox.<username>.workers.dev`

---

### 3. Masukkan Konfigurasi ke PetaniProxy
Buka menu `[K] Pusat Pengaturan` di PetaniProxy atau edit langsung file `config/settings.json`:
```json
{
  "cf_domains": "domainku.com",
  "cf_worker_url": "https://petani-proxy-inbox.<username>.workers.dev",
  "cf_worker_secret": "TokenRahasiaBansos123"
}
```

> 💡 **Tip:** Jika Anda sudah memiliki Worker aktif dari proyek `github-farm`, Anda bisa langsung menggunakan URL & Secret yang sama tanpa perlu men-deploy Worker baru!
