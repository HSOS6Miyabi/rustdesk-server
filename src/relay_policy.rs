//! Optional relay selection using IP ranges supplied by the OSS API.
use ipnetwork::IpNetwork;
use serde_derive::Deserialize;
use std::{
    env,
    net::IpAddr,
    str::FromStr,
    sync::atomic::{AtomicUsize, Ordering},
    time::Duration,
};

#[derive(Clone, Debug)]
pub(crate) struct RelayRule {
    pub(crate) address: String,
    pub(crate) priority: i32,
    networks: Vec<IpNetwork>,
}

#[derive(Clone, Debug, Default)]
pub(crate) struct RelayPolicy {
    pub(crate) nodes: Vec<RelayRule>,
}

#[derive(Deserialize)]
struct RelayFeed {
    nodes: Vec<RelayNode>,
}

#[derive(Deserialize)]
struct RelayNode {
    address: String,
    priority: i32,
    #[serde(default)]
    subnets: Vec<String>,
}

pub(crate) fn managed() -> bool {
    env::var("RUSTDESK_API_RELAY_NODES_URL")
        .map(|url| !url.trim().is_empty())
        .unwrap_or(false)
}

pub(crate) fn refresh_seconds() -> u64 {
    env::var("RUSTDESK_API_RELAY_SYNC_SECONDS")
        .ok()
        .and_then(|value| value.parse::<u64>().ok())
        .unwrap_or(30)
        .clamp(10, 3600)
}

fn parse_feed(body: &str) -> Result<RelayPolicy, String> {
    let data: RelayFeed = serde_json::from_str(body).map_err(|e| e.to_string())?;
    if data.nodes.len() > 64 {
        return Err("relay feed includes more than 64 nodes".to_owned());
    }
    let mut result = RelayPolicy::default();
    for node in data.nodes {
        if node.address.is_empty()
            || node.address.len() > 253
            || !node
                .address
                .chars()
                .all(|c| c.is_ascii_alphanumeric() || ".-:[]".contains(c))
        {
            return Err(format!("relay address is invalid: {}", node.address));
        }
        if node.priority < 0 || node.priority > 10000 || node.subnets.len() > 64 {
            return Err("relay priority or network count is out of range".to_owned());
        }
        if result.nodes.iter().any(|current| current.address == node.address) {
            return Err("relay feed has duplicate addresses".to_owned());
        }
        let networks = node
            .subnets
            .iter()
            .map(|cidr| IpNetwork::from_str(cidr).map_err(|e| e.to_string()))
            .collect::<Result<Vec<_>, _>>()?;
        result.nodes.push(RelayRule {
            address: node.address,
            priority: node.priority,
            networks,
        });
    }
    result
        .nodes
        .sort_by(|a, b| a.priority.cmp(&b.priority).then(a.address.cmp(&b.address)));
    Ok(result)
}

pub(crate) async fn fetch() -> Result<Option<RelayPolicy>, String> {
    let url = match env::var("RUSTDESK_API_RELAY_NODES_URL") {
        Ok(value) if !value.trim().is_empty() => value,
        _ => return Ok(None),
    };
    if !url.starts_with("http://") && !url.starts_with("https://") {
        return Err("relay node URL must begin with http:// or https://".to_owned());
    }
    let key = env::var("RUSTDESK_API_INTERNAL_KEY")
        .map_err(|_| "RUSTDESK_API_INTERNAL_KEY is required for relay synchronization".to_owned())?;
    if key.is_empty() {
        return Err("RUSTDESK_API_INTERNAL_KEY is required for relay synchronization".to_owned());
    }
    let body = hbb_common::tokio::task::spawn_blocking(move || {
        let client = reqwest::blocking::Client::builder()
            .timeout(Duration::from_secs(5))
            .build()
            .map_err(|err| err.to_string())?;
        let response = client
            .get(url)
            .header("X-RustDesk-Internal-Key", key)
            .send()
            .map_err(|err| err.to_string())?;
        if !response.status().is_success() {
            return Err(format!("relay node API returned HTTP {}", response.status()));
        }
        response.text().map_err(|err| err.to_string())
    })
    .await
    .map_err(|err| err.to_string())??;
    parse_feed(&body).map(Some)
}

// Choose a healthy relay matching both peers if possible. When no network
// preferences match, retain the OSS server's round-robin behavior.
pub(crate) fn select(
    policy: &RelayPolicy,
    active: &[String],
    peer_a: IpAddr,
    peer_b: IpAddr,
    rotation: &AtomicUsize,
) -> String {
    if active.is_empty() {
        return String::new();
    }
    if active.len() == 1 {
        return active[0].clone();
    }
    let mut score = 0usize;
    let mut priority = i32::MAX;
    let mut preferred: Vec<&str> = Vec::new();
    for node in &policy.nodes {
        if !active.iter().any(|address| address == &node.address) {
            continue;
        }
        let matched_a = node.networks.iter().any(|network| network.contains(peer_a));
        let matched_b = node.networks.iter().any(|network| network.contains(peer_b));
        let candidate_score = matched_a as usize + matched_b as usize;
        if candidate_score == 0 {
            continue;
        }
        if candidate_score > score || (candidate_score == score && node.priority < priority) {
            score = candidate_score;
            priority = node.priority;
            preferred.clear();
        }
        if candidate_score == score && node.priority == priority {
            preferred.push(&node.address);
        }
    }
    if !preferred.is_empty() {
        return preferred[rotation.fetch_add(1, Ordering::SeqCst) % preferred.len()].to_owned();
    }
    active[rotation.fetch_add(1, Ordering::SeqCst) % active.len()].clone()
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::net::IpAddr;

    fn parsed(value: &str) -> IpAddr {
        value.parse().unwrap()
    }

    #[test]
    fn selects_matching_healthy_nodes_and_falls_back() {
        let policy = parse_feed(
            r#"{"nodes":[
                {"address":"relay-a.example:21117","priority":10,"subnets":["203.0.113.0/24"]},
                {"address":"relay-b.example:21117","priority":20,"subnets":["198.51.100.0/24"]},
                {"address":"relay-c.example:21117","priority":30,"subnets":[]}
            ]}"#,
        ).unwrap();
        let active = policy.nodes.iter().map(|item| item.address.clone()).collect::<Vec<_>>();
        let counter = AtomicUsize::new(0);
        assert_eq!(
            select(&policy, &active, parsed("203.0.113.4"), parsed("192.0.2.10"), &counter),
            "relay-a.example:21117",
        );
        assert_eq!(
            select(&policy, &active, parsed("198.51.100.20"), parsed("198.51.100.21"), &counter),
            "relay-b.example:21117",
        );
        let healthy = vec!["relay-b.example:21117".into(), "relay-c.example:21117".into()];
        assert_eq!(
            select(&policy, &healthy, parsed("203.0.113.10"), parsed("192.0.2.10"), &counter),
            "relay-b.example:21117",
        );
        assert_eq!(
            select(&policy, &active, parsed("10.0.0.1"), parsed("10.0.0.2"), &counter),
            active[counter.load(Ordering::SeqCst).wrapping_sub(1) % active.len()],
        );
        assert!(select(&policy, &[], parsed("127.0.0.1"), parsed("127.0.0.1"), &counter).is_empty());
    }

    #[test]
    fn rejects_invalid_rules_and_supports_ipv6() {
        assert!(parse_feed(r#"{"nodes":[{"address":"bad host","priority":1,"subnets":[]}]}"#).is_err());
        assert!(parse_feed(r#"{"nodes":[{"address":"a","priority":1,"subnets":["not a CIDR"]}]}"#).is_err());
        let policy=parse_feed(r#"{"nodes":[
            {"address":"[2001:db8::1]:21117","priority":1,"subnets":["2001:db8:1::/48"]},
            {"address":"relay-backup","priority":20,"subnets":[]}
        ]}"#).unwrap();
        let available=policy.nodes.iter().map(|node|node.address.clone()).collect::<Vec<_>>();
        assert_eq!(
            select(&policy,&available,parsed("2001:db8:1::42"),parsed("2001:db8:2::42"),&AtomicUsize::new(0)),
            "[2001:db8::1]:21117"
        );
    }

    #[test]
    fn empty_feed_keeps_default_server_configuration_available() {
        assert!(parse_feed(r#"{"nodes":[]}"#).unwrap().nodes.is_empty());
        assert!(parse_feed("garbage").is_err());
    }
}
