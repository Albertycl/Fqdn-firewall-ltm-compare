-- Demo data for the FQDN lookup (made-up records, documentation-range IPs only).
-- Re-runnable: tables are created if missing and the demo rows are replaced.
--
--   docker exec -i -e MYSQL_PWD='<password>' <db-container> mariadb -u<user> fqdn_v3 < demo/seed_fqdn_demo.sql
--
-- The fqdn_v3 database must already exist (demo/initdb creates it for the bundled database).
--
-- The portal reads these two tables from the fqdn_v3 database.

-- Columns match backend/blueprint/search/routes.py (query_fqdn_database, get_fqdn_for_public_ips).
CREATE TABLE IF NOT EXISTS fqdn_new (
  id      INT AUTO_INCREMENT PRIMARY KEY,
  owner   VARCHAR(100),
  domain  VARCHAR(255) NOT NULL,
  fqdn    VARCHAR(255) NOT NULL,
  ttl     INT,
  type_   VARCHAR(10),
  ip      VARCHAR(45),
  geoInfo VARCHAR(255),
  KEY idx_ip (ip),
  KEY idx_fqdn (fqdn)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Columns match query_slbs_by_fqdn_pattern. v_pool is a JSON list:
-- ["<pool name>", "<member ip>:<port>", ...]. v_env: 1=Alpha 2=Bravo 3=Charlie 4=Delta 5=UAT 6=ADMIN 7=LOADTEST.
CREATE TABLE IF NOT EXISTS slbs (
  id        INT AUTO_INCREMENT PRIMARY KEY,
  v_name    VARCHAR(255) NOT NULL,
  v_ip      VARCHAR(45),
  v_service VARCHAR(16),
  v_pool    TEXT,
  v_env     INT NOT NULL,
  KEY idx_name (v_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DELETE FROM fqdn_new WHERE owner = 'demo';
INSERT INTO fqdn_new (owner, domain, fqdn, ttl, type_, ip, geoInfo) VALUES
  ('demo', 'demo-corp.example', 'www.demo-corp.example',           300, 'A',     '203.0.113.10', 'Taipei, TW'),
  ('demo', 'demo-corp.example', 'sb-results.demo-corp.example',    300, 'A',     '203.0.113.21', 'Taipei, TW'),
  ('demo', 'demo-corp.example', 'sb-odds.demo-corp.example',       300, 'A',     '203.0.113.22', 'Taipei, TW'),
  ('demo', 'demo-corp.example', 'api.demo-corp.example',           60,  'A',     '198.51.100.5', 'Singapore, SG'),
  ('demo', 'demo-corp.example', 'api.demo-corp.example',           60,  'A',     '198.51.100.6', 'Singapore, SG'),
  ('demo', 'demo-corp.example', 'static.demo-corp.example',        3600,'CNAME', NULL,           NULL),
  ('demo', 'demo-shop.example', 'shop.demo-shop.example',          300, 'A',     '203.0.113.40', 'Tokyo, JP'),
  ('demo', 'demo-shop.example', 'checkout.demo-shop.example',      300, 'A',     '203.0.113.41', 'Tokyo, JP');

DELETE FROM slbs WHERE v_name LIKE 'DEMO\_%';
-- No SBR_Results rows here on purpose: the LTM demo rows in seed_firewall_demo.sql already
-- give each infra (Alpha/Bravo/Charlie) one virtual server for sb-results, so a second
-- copy from this table would show up as a duplicate card.
INSERT INTO slbs (v_name, v_ip, v_service, v_pool, v_env) VALUES
  ('DEMO_SBO_Odds_443_Alpha', '203.0.113.22', '443', '["pool_demo_sbo_alpha", "192.0.2.21:8443"]',                1),
  ('DEMO_Shop_443_Bravo',     '203.0.113.40', '443', '["pool_demo_shop", "192.0.2.41:8080", "192.0.2.42:8080"]', 2);
