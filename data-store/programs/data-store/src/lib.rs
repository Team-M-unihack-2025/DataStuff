use anchor_lang::prelude::*;

declare_id!("GDMu4vZGC87ER1BNJqTr7ecJE2hXz47WATZFrBD44mB6");

#[program]
pub mod data_store {
    use super::*;

    pub fn initialize_node(ctx: Context<InitializeNode>, key: String, data_len: u32) -> Result<()> {
        let node = &mut ctx.accounts.node_account;
        node.key = key;
        node.data = vec![0; data_len as usize];
        node.bump = ctx.bumps.node_account;
        Ok(())
    }

    pub fn store_node(ctx: Context<StoreNode>, _key: String, data: Vec<u8>) -> Result<()> {
        let node = &mut ctx.accounts.node_account;
        require!(data.len() <= node.data.len(), ErrorCode::DataTooLarge);
        node.data.copy_from_slice(&data);
        Ok(())
    }

    // New: allow growing/shrinking the PDA to fit payloads
    pub fn resize_node(ctx: Context<ResizeNode>, key: String, new_len: u32) -> Result<()> {
        let node = &mut ctx.accounts.node_account;

        // Safety: make sure we are resizing the expected node
        require!(node.key == key, ErrorCode::KeyMismatch);

        // Ensure internal vec matches the new space
        node.data.resize(new_len as usize, 0);
        Ok(())
    }
}

#[derive(Accounts)]
#[instruction(key: String, data_len: u32)]
pub struct InitializeNode<'info> {
    #[account(
        init,
        payer = payer,
        space = 8 + 4 + key.len() + 4 + data_len as usize + 1,
        seeds = [b"node", key.as_bytes()],
        bump
    )]
    pub node_account: Account<'info, NodeAccount>,

    #[account(mut)]
    pub payer: Signer<'info>,

    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
#[instruction(key: String)]
pub struct StoreNode<'info> {
    #[account(
        mut,
        seeds = [b"node", key.as_bytes()],
        bump = node_account.bump
    )]
    pub node_account: Account<'info, NodeAccount>,
}

#[derive(Accounts)]
#[instruction(key: String, new_len: u32)]
pub struct ResizeNode<'info> {
    #[account(
        mut,
        seeds = [b"node", key.as_bytes()],
        bump = node_account.bump,
        realloc = 8 + 4 + key.len() + 4 + new_len as usize + 1,
        realloc::payer = payer,
        realloc::zero = true
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

#[error_code]
pub enum ErrorCode {
    #[msg("Data exceeds preallocated space")]
    DataTooLarge,
    #[msg("Key mismatch for node resize")]
    KeyMismatch,
}
