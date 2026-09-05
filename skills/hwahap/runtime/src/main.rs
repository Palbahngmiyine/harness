//! `hwahap` — a local STDIO MCP server.
//!
//! There is no daemon, no HTTP endpoint, and no other subcommand. The host starts this process,
//! speaks MCP over stdin and stdout, and stops it. Everything durable lives in the repository's
//! `.hwahap/` directory, so a restart loses nothing.

use hwahap::mcp::Hwahap;
use rmcp::transport::stdio;
use rmcp::ServiceExt;

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    // stdout belongs to the MCP transport. Anything Hwahap wants a human to see goes to stderr,
    // and anything it wants to keep goes into `.hwahap/`.
    let server = Hwahap::new();
    let service = server.clone().serve(stdio()).await?;

    let token = service.cancellation_token();
    tokio::spawn(async move {
        if tokio::signal::ctrl_c().await.is_ok() {
            token.cancel();
        }
    });

    let quit_reason = service.waiting().await;
    server.shutdown().await;
    let quit_reason = quit_reason?;
    eprintln!("hwahap exited: {quit_reason:?}");

    // `tokio::io::stdin()` parks a blocking-pool thread in a `read` that only returns at EOF, and
    // dropping the runtime waits for that pool. After a cancellation the read is still parked, so
    // returning from main here hangs forever. Exiting explicitly is what actually leaves no
    // process behind, which is one of Hwahap's stated guarantees.
    std::process::exit(0);
}
