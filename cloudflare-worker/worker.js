/**
 * PetaniProxy — Cloudflare Email Worker
 * 
 * Email Routing Handler + HTTP Inbox API
 *
 * Alur:
 *   1. Email masuk ke domain Anda yang diarahkan ke Cloudflare Email Routing Catch-all (*@domain).
 *   2. Cloudflare meneruskan pesan ke Worker ini.
 *   3. Worker mem-parse pesan menggunakan postal-mime dan menyimpannya di Workers KV dengan TTL 1 jam.
 *   4. Script PetaniProxy memanggil GET /inbox?address=<email> dengan header X-Worker-Secret untuk
 *      mengekstrak link verifikasi secara otomatis.
 *
 * Cara Deploy:
 *   1. Masuk ke folder: cd cloudflare-worker
 *   2. Install dependensi: npm install
 *   3. Buat KV Namespace: npx wrangler kv namespace create INBOX
 *   4. Salin ID KV ke wrangler.toml
 *   5. Set secret: npx wrangler secret put WORKER_SECRET
 *   6. Deploy: npx wrangler deploy
 */

import PostalMime from "postal-mime";

function toPlainText(html) {
  return String(html || "")
    .replace(/<style[\s\S]*?<\/style>/gi, " ")
    .replace(/<script[\s\S]*?<\/script>/gi, " ")
    .replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/\s+/g, " ")
    .trim();
}

export default {
  // ---- Email Routing handler ----
  async email(message, env, ctx) {
    const to = (message.to || "").toLowerCase().trim();
    if (!to) return;

    const raw = new Response(message.raw).body;
    const parsed = await PostalMime.parse(raw);

    const body = toPlainText(parsed.text || parsed.html || "");
    const record = {
      from: parsed.from?.address || message.from || "",
      subject: parsed.subject || "",
      body,
      html: parsed.html || "",
      date: new Date().toISOString(),
    };

    const ts = Date.now();
    const key = `msg:${to}:${ts}:${crypto.randomUUID().slice(0, 8)}`;
    // Simpan di KV dengan TTL 3600 detik (1 jam)
    ctx.waitUntil(env.INBOX.put(key, JSON.stringify(record), { expirationTtl: 3600 }));
  },

  // ---- HTTP inbox API ----
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    if (url.pathname !== "/inbox") {
      return json({ ok: false, error: "not found" }, 404);
    }

    // Validasi shared secret header
    const secret = request.headers.get("X-Worker-Secret") || "";
    if (env.WORKER_SECRET && secret !== env.WORKER_SECRET) {
      return json({ ok: false, error: "unauthorized" }, 401);
    }

    const address = (url.searchParams.get("address") || "").toLowerCase().trim();
    if (!address || !/^[^@\s]+@[^@\s]+$/.test(address)) {
      return json({ ok: false, error: "address query param required" }, 400);
    }

    const prefix = `msg:${address}:`;
    const list = await env.INBOX.list({ prefix, limit: 100 });
    const messages = [];
    for (const key of list.keys) {
      const raw = await env.INBOX.get(key.name);
      if (!raw) continue;
      try {
        messages.push(JSON.parse(raw));
      } catch {
        // Skip data corrupt
      }
    }

    // Urutkan pesan dari yang terlama ke yang terbaru
    messages.sort((a, b) => String(a.date).localeCompare(String(b.date)));

    return json({ ok: true, address, messages });
  },
};

function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { "content-type": "application/json" },
  });
}
