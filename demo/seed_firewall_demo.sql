-- Demo firewall + LTM rows so a search for sb-results.demo-corp.example (203.0.113.21)
-- shows a DIFFERENT result per infrastructure: Alpha, Bravo, Charlie.
-- Made-up data, documentation-range IPs. Re-runnable: only rows named DEMO... are replaced.
-- Needs the fqdn_tool tables, which the backend creates on start-up.
-- NOTE: the daily update clears parsed data, so run this again after it.
--
-- Use demo/load-demo-data.sh, or:
--   docker exec -i -e MYSQL_PWD='<password>' <db-container> mariadb -u<user> fqdn_tool < demo/seed_firewall_demo.sql

-- Make sure one (made-up) parsed config file exists per device. A real install that already
-- has parsed files keeps them: the demo rows then attach to the newest existing one.
INSERT INTO config_files (filename, file_type, file_path, upload_date, parsed_status)
SELECT d.fn, d.ft, CONCAT('demo/', d.fn), NOW(), 'parsed'
FROM (SELECT 'ALPHA-FW01_demo.txt' AS fn, 'firewall' AS ft, 'ALPHA-FW01' AS pat UNION ALL
      SELECT 'ALPHA-LTM01_demo.txt', 'ltm',      'ALPHA-LTM01' UNION ALL
      SELECT 'BRAVO-FW01_demo.txt',  'firewall', 'BRAVO-FW01'  UNION ALL
      SELECT 'BRAVO-LTM01_demo.txt', 'ltm',      'BRAVO-LTM01' UNION ALL
      SELECT 'CHARLIE-FW01_demo.txt',  'firewall', 'CHARLIE-FW01'  UNION ALL
      SELECT 'CHARLIE-LTM01_demo.txt', 'ltm',      'CHARLIE-LTM01') d
WHERE NOT EXISTS (SELECT 1 FROM config_files c WHERE c.filename LIKE CONCAT(d.pat, '%'));

SET @alpha_fw  = (SELECT MAX(id) FROM config_files WHERE filename LIKE 'ALPHA-FW01%');
SET @alpha_ltm = (SELECT MAX(id) FROM config_files WHERE filename LIKE 'ALPHA-LTM01%');
SET @bravo_fw  = (SELECT MAX(id) FROM config_files WHERE filename LIKE 'BRAVO-FW01%');
SET @bravo_ltm = (SELECT MAX(id) FROM config_files WHERE filename LIKE 'BRAVO-LTM01%');
SET @charlie_fw  = (SELECT MAX(id) FROM config_files WHERE filename LIKE 'CHARLIE-FW01%');
SET @charlie_ltm = (SELECT MAX(id) FROM config_files WHERE filename LIKE 'CHARLIE-LTM01%');

DELETE FROM firewall_policies        WHERE policy_id LIKE 'DEMO-%';
DELETE FROM firewall_address_groups  WHERE name LIKE 'DEMO\_%';
DELETE FROM firewall_address_objects WHERE name LIKE 'DEMO\_%';
DELETE FROM ltm_nodes            WHERE node_name LIKE 'DEMO\_%';
DELETE FROM ltm_pools            WHERE name LIKE '/Common/DEMO\_%';
DELETE FROM ltm_virtual_servers  WHERE name LIKE '/Common/DEMO\_%';

-- ===== Alpha: host object, group of two VIPs, one HTTPS accept policy, 2 healthy nodes =====
INSERT INTO firewall_address_objects (config_file_id, name, ip_address, subnet_mask, cidr_notation, object_type) VALUES
  (@alpha_fw, 'DEMO_alpha_sb-results_vip', '203.0.113.21', '255.255.255.255', '203.0.113.21/32', 'host'),
  (@alpha_fw, 'DEMO_alpha_sb-odds_vip',    '203.0.113.22', '255.255.255.255', '203.0.113.22/32', 'host'),
  (@alpha_fw, 'DEMO_alpha_office',         '198.51.100.0', '255.255.255.0',   '198.51.100.0/24', 'subnet');
INSERT INTO firewall_address_groups (config_file_id, name, members, resolved_members, member_count, member_details) VALUES
  (@alpha_fw, 'DEMO_alpha_GRP_sportsbook',
   '["DEMO_alpha_sb-results_vip", "DEMO_alpha_sb-odds_vip"]', '["203.0.113.21", "203.0.113.22"]', 2,
   '[{"name": "DEMO_alpha_sb-results_vip", "ip": "203.0.113.21", "type": "address"}, {"name": "DEMO_alpha_sb-odds_vip", "ip": "203.0.113.22", "type": "address"}]');
INSERT INTO firewall_policies (config_file_id, policy_id, name, source_addresses, destination_addresses, source_zone, destination_zone, services, action, status) VALUES
  (@alpha_fw, 'DEMO-A1', 'DEMO alpha office to sportsbook HTTPS', '["DEMO_alpha_office"]', '["DEMO_alpha_GRP_sportsbook"]', 'vw1', 'vw2', '["HTTPS"]', 'accept', 'enable');
INSERT INTO ltm_pools (config_file_id, name, monitor, load_balancing_method) VALUES
  (@alpha_ltm, '/Common/DEMO_po_alpha_SBR_443', '/Common/tcp', 'round-robin');
SET @pool = LAST_INSERT_ID();
INSERT INTO ltm_nodes (config_file_id, pool_id, ip_address, port, status, node_name) VALUES
  (@alpha_ltm, @pool, '192.0.2.11', '8443', 'up', 'DEMO_alpha_node_11'),
  (@alpha_ltm, @pool, '192.0.2.12', '8443', 'up', 'DEMO_alpha_node_12');
INSERT INTO ltm_virtual_servers (config_file_id, name, destination_ip, destination_port, pool_name, enabled) VALUES
  (@alpha_ltm, '/Common/DEMO_vs_alpha_SBR_443', '/Common/203.0.113.21', 443, '/Common/DEMO_po_alpha_SBR_443', 1);

-- ===== Bravo: /24 subnet match, two policies (HTTPS accept + SSH deny), 1 node on port 8080 =====
INSERT INTO firewall_address_objects (config_file_id, name, ip_address, subnet_mask, cidr_notation, object_type) VALUES
  (@bravo_fw, 'DEMO_bravo_dmz',      '203.0.113.0', '255.255.255.0', '203.0.113.0/24', 'subnet'),
  (@bravo_fw, 'DEMO_bravo_partners', '192.0.2.128', '255.255.255.128', '192.0.2.128/25', 'subnet');
INSERT INTO firewall_policies (config_file_id, policy_id, name, source_addresses, destination_addresses, source_zone, destination_zone, services, action, status) VALUES
  (@bravo_fw, 'DEMO-B1', 'DEMO bravo partners to DMZ web',   '["DEMO_bravo_partners"]', '["DEMO_bravo_dmz"]', 'ext', 'dmz', '["HTTP", "HTTPS"]', 'accept', 'enable'),
  (@bravo_fw, 'DEMO-B2', 'DEMO bravo block SSH to DMZ',      '["all"]',                 '["DEMO_bravo_dmz"]', 'ext', 'dmz', '["SSH"]',           'deny',   'enable');
INSERT INTO ltm_pools (config_file_id, name, monitor, load_balancing_method) VALUES
  (@bravo_ltm, '/Common/DEMO_po_bravo_SBR_8080', '/Common/http', 'least-connections-member');
SET @pool = LAST_INSERT_ID();
INSERT INTO ltm_nodes (config_file_id, pool_id, ip_address, port, status, node_name) VALUES
  (@bravo_ltm, @pool, '192.0.2.51', '8080', 'up', 'DEMO_bravo_node_51');
INSERT INTO ltm_virtual_servers (config_file_id, name, destination_ip, destination_port, pool_name, enabled) VALUES
  (@bravo_ltm, '/Common/DEMO_vs_bravo_SBR_80', '/Common/203.0.113.21', 80, '/Common/DEMO_po_bravo_SBR_8080', 1);

-- ===== Charlie: single-VIP group, a disabled policy, 3 nodes, one VS disabled =====
INSERT INTO firewall_address_objects (config_file_id, name, ip_address, subnet_mask, cidr_notation, object_type) VALUES
  (@charlie_fw, 'DEMO_charlie_results_vip', '203.0.113.21', '255.255.255.255', '203.0.113.21/32', 'host'),
  (@charlie_fw, 'DEMO_charlie_monitor',     '198.51.100.200', '255.255.255.255', '198.51.100.200/32', 'host');
INSERT INTO firewall_address_groups (config_file_id, name, members, resolved_members, member_count, member_details) VALUES
  (@charlie_fw, 'DEMO_charlie_GRP_results', '["DEMO_charlie_results_vip"]', '["203.0.113.21"]', 1,
   '[{"name": "DEMO_charlie_results_vip", "ip": "203.0.113.21", "type": "address"}]');
INSERT INTO firewall_policies (config_file_id, policy_id, name, source_addresses, destination_addresses, source_zone, destination_zone, services, action, status) VALUES
  (@charlie_fw, 'DEMO-C1', 'DEMO charlie monitor to results ICMP+HTTPS', '["DEMO_charlie_monitor"]', '["DEMO_charlie_GRP_results"]', 'mgmt', 'vw2', '["PING", "HTTPS"]', 'accept', 'enable'),
  (@charlie_fw, 'DEMO-C2', 'DEMO charlie old rule (disabled)',           '["all"]',                  '["DEMO_charlie_results_vip"]',  'vw1',  'vw2', '["ALL"]',          'accept', 'disable');
INSERT INTO ltm_pools (config_file_id, name, monitor, load_balancing_method) VALUES
  (@charlie_ltm, '/Common/DEMO_po_charlie_SBR_9443', '/Common/https', 'ratio-member');
SET @pool = LAST_INSERT_ID();
INSERT INTO ltm_nodes (config_file_id, pool_id, ip_address, port, status, node_name) VALUES
  (@charlie_ltm, @pool, '192.0.2.71', '9443', 'up',   'DEMO_charlie_node_71'),
  (@charlie_ltm, @pool, '192.0.2.72', '9443', 'up',   'DEMO_charlie_node_72'),
  (@charlie_ltm, @pool, '192.0.2.73', '9443', 'down', 'DEMO_charlie_node_73');
INSERT INTO ltm_virtual_servers (config_file_id, name, destination_ip, destination_port, pool_name, enabled) VALUES
  (@charlie_ltm, '/Common/DEMO_vs_charlie_SBR_9443', '/Common/203.0.113.21', 9443, '/Common/DEMO_po_charlie_SBR_9443', 0);
