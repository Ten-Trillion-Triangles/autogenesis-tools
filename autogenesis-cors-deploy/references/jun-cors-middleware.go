# Jun's `corsMiddleware` — exact implementation

From `Junaili/chess` → `custom-extend-app/ethan-chess-service/cmd/main.go`

## `parseAllowedOrigins` (lines 341–354)

```go
// parseAllowedOrigins merges optional deployment-specific origins with the
// shipped web, local-development, and Capacitor origins. Keeping these defaults
// additive prevents ALLOWED_ORIGIN from accidentally disabling the iOS app.
func parseAllowedOrigins(raw string) map[string]struct{} {
    defaults := []string{
        "https://junaili.github.io",
        "https://localhost:8808",
        "capacitor://localhost",
    }
    set := make(map[string]struct{})
    for _, o := range defaults {
        set[o] = struct{}{}
    }
    for _, o := range strings.Split(raw, ",") {
        o = strings.TrimSpace(o)
        if o != "" {
            set[o] = struct{}{}
        }
    }
    return set
}
```

## `corsMiddleware` (lines 356–372)

```go
func corsMiddleware(allowed map[string]struct{}, next http.Handler) http.Handler {
    return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        origin := r.Header.Get("Origin")
        if origin != "" {
            if _, ok := allowed[origin]; !ok {
                http.Error(w, `{"error":"origin not allowed"}`, http.StatusForbidden)
                return
            }
            w.Header().Set("Access-Control-Allow-Origin", origin)
            w.Header().Set("Vary", "Origin")
        }
        // DELETE covers family disband (DELETE /group/v1/.../groups/{id}).
        w.Header().Set("Access-Control-Allow-Methods", "POST, GET, DELETE, OPTIONS")
        w.Header().Set("Access-Control-Allow-Headers", "Authorization, Content-Type")
        w.Header().Set("Access-Control-Allow-Credentials", "true")
        if r.Method == http.MethodOptions {
            w.WriteHeader(http.StatusNoContent)
            return
        }
        next.ServeHTTP(w, r)
    })
}
```

## `playerAuthorizationHeader` (cookie-as-fallback for ingress-stripped-Authorization)

```go
func playerAuthorizationHeader(r *http.Request) string {
    if header := r.Header.Get("Authorization"); header != "" {
        return header
    }
    if cookie, err := r.Cookie("access_token"); err == nil && cookie.Value != "" {
        return "Bearer " + cookie.Value
    }
    return ""
}
```

## Key load-bearing properties (for Ktor porting)

1. **Exact-map-lookup origin validation** — `allowed[origin]` not regex, not suffix-strip. Unknown origins get 403, not ignored.
2. **`Vary: Origin`** on every response with a Origin header — CDN cache cannot collapse per-origin responses.
3. **`Access-Control-Allow-Credentials: true`** — browser attaches HttpOnly cookie on cross-origin requests. Without this, cookie-based auth silently fails on CORS requests.
4. **OPTIONS returns 204 NoContent then exits** — preflight handled entirely in middleware, `next.ServeHTTP` not called.
5. **`Authorization` header takes precedence over cookie** — server-to-server calls (tooling, other services) use Bearer token; browser calls fall back to cookie.
