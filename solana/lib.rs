// programs/data-store/src/lib.rs
use anchor_lang::prelude::*;

declare_id!("YourProgramIDWillGoHere11111111111111111");

#[program]
pub mod data_store {
    use super::*;

    pub fn store_node(ctx: Context<StoreNode>, key: String, data: Vec<u8>) -> Result<()> {
        let node_account = &mut ctx.accounts.node_account;
        node_account.key = key;
        node_account.data = data;
        node_account.bump = ctx.bumps.node_account;
        Ok(())
    }
}

#[derive(Accounts)]
#[instruction(key: String)]
pub struct StoreNode<'info> {
    #[account(
        init,
        payer = payer,
        space = 8 + 4 + key.len() + 4 + 10240 + 1, // discriminator + key + data + bump
        seeds = [b"node", key.as_bytes()],
        bump
    )]
    pub node_account: Account<'info, NodeAccount>,

    #[account(mut)]
    pub payer: Signer<'info>,

    pub system_program: Program<'info, System>,
}

#[account]
pub struct NodeAccount {
    pub key: String,
    pub data: Vec<u8>,
    pub bump: u8,
}
