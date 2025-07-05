/**
 * Cypress E2E test for FeedMe Supabase integration
 * Tests the conversation approval workflow and Supabase persistence
 */

describe('FeedMe Supabase Integration', () => {
  beforeEach(() => {
    // Visit the FeedMe page
    cy.visit('/feedme')
    
    // Wait for initial load
    cy.get('[data-testid="feedme-container"]').should('be.visible')
  })

  it('should approve conversation and sync to Supabase', () => {
    // Mock API responses
    cy.intercept('GET', '/api/v1/feedme/conversations*', {
      statusCode: 200,
      body: {
        conversations: [
          {
            id: 1,
            title: 'Test Conversation for Supabase',
            processing_status: 'completed',
            total_examples: 3,
            created_at: new Date().toISOString(),
            metadata: {},
            folder_id: 1
          }
        ],
        total_count: 1,
        page: 1,
        page_size: 20,
        has_next: false
      }
    }).as('getConversations')

    cy.intercept('GET', '/api/v1/feedme/conversations/1/examples', {
      statusCode: 200,
      body: {
        examples: [
          {
            id: 1,
            conversation_id: 1,
            question_text: 'How do I reset my password?',
            answer_text: 'Go to Settings > Account > Reset Password',
            confidence_score: 0.85,
            is_active: true
          },
          {
            id: 2,
            conversation_id: 1,
            question_text: 'Email sync not working',
            answer_text: 'Check your server settings and credentials',
            confidence_score: 0.90,
            is_active: true
          },
          {
            id: 3,
            conversation_id: 1,
            question_text: 'How to add multiple accounts?',
            answer_text: 'Click Add Account button in the sidebar',
            confidence_score: 0.80,
            is_active: true
          }
        ],
        total_examples: 3
      }
    }).as('getExamples')

    // Mock Supabase approval endpoint
    cy.intercept('POST', '/api/v1/feedme/conversations/1/examples/approve', {
      statusCode: 200,
      body: {
        conversation_id: 1,
        approved_count: 3,
        approved_by: 'test@example.com',
        approved_at: new Date().toISOString(),
        example_ids: [1, 2, 3],
        supabase_sync: 'pending',
        message: 'Successfully approved 3 examples. Supabase sync in progress.'
      }
    }).as('approveConversation')

    // Wait for conversations to load
    cy.wait('@getConversations')

    // Click on the conversation
    cy.contains('Test Conversation for Supabase').click()

    // Wait for examples to load
    cy.wait('@getExamples')

    // Click approve button
    cy.get('[data-testid="approve-conversation-button"]').click()

    // Fill approval dialog
    cy.get('[data-testid="approval-dialog"]').within(() => {
      cy.get('input[name="approved_by"]').type('test@example.com')
      cy.get('textarea[name="reviewer_notes"]').type('Good quality examples for testing')
      cy.get('button[type="submit"]').click()
    })

    // Wait for approval request
    cy.wait('@approveConversation')

    // Verify success toast
    cy.get('[data-testid="toast"]')
      .should('contain', 'Conversation Approved')
      .and('contain', 'Successfully approved 3 examples')
      .and('contain', 'Syncing to Supabase')

    // Verify conversation status updated
    cy.get('[data-testid="conversation-status"]')
      .should('contain', 'approved')
  })

  it('should handle folder assignment with Supabase sync', () => {
    // Mock folder list
    cy.intercept('GET', '/api/v1/feedme/folders', {
      statusCode: 200,
      body: {
        folders: [
          { id: 1, name: 'General', color: '#0095ff', conversation_count: 5 },
          { id: 2, name: 'Bugs', color: '#ef4444', conversation_count: 3 },
          { id: 3, name: 'Features', color: '#10b981', conversation_count: 2 }
        ],
        total_count: 3
      }
    }).as('getFolders')

    // Mock folder assignment endpoint
    cy.intercept('PUT', '/api/v1/feedme/folders/2/assign', {
      statusCode: 200,
      body: {
        folder_id: 2,
        folder_name: 'Bugs',
        assigned_count: 1,
        conversation_ids: [1],
        supabase_sync: 'pending',
        message: "Successfully assigned 1 conversations to folder 'Bugs'"
      }
    }).as('assignToFolder')

    // Select a conversation
    cy.get('[data-testid="conversation-checkbox-1"]').click()

    // Open bulk actions menu
    cy.get('[data-testid="bulk-actions-button"]').click()

    // Click move to folder
    cy.get('[data-testid="move-to-folder-option"]').click()

    // Wait for folders to load
    cy.wait('@getFolders')

    // Select "Bugs" folder
    cy.get('[data-testid="folder-select-dialog"]').within(() => {
      cy.contains('Bugs').click()
      cy.get('button[type="submit"]').click()
    })

    // Wait for assignment
    cy.wait('@assignToFolder')

    // Verify success message
    cy.get('[data-testid="toast"]')
      .should('contain', 'Successfully assigned 1 conversations to folder')
  })

  it('should approve specific examples only', () => {
    // Mock getting examples
    cy.intercept('GET', '/api/v1/feedme/conversations/1/examples', {
      statusCode: 200,
      body: {
        examples: [
          {
            id: 1,
            question_text: 'How do I reset my password?',
            answer_text: 'Go to Settings',
            confidence_score: 0.85,
            is_active: true
          },
          {
            id: 2,
            question_text: 'Email sync issue',
            answer_text: 'Check settings',
            confidence_score: 0.60,
            is_active: true
          }
        ]
      }
    }).as('getExamples')

    // Mock approval with specific IDs
    cy.intercept('POST', '/api/v1/feedme/conversations/1/examples/approve', (req) => {
      expect(req.body.example_ids).to.deep.equal([1])
      req.reply({
        statusCode: 200,
        body: {
          conversation_id: 1,
          approved_count: 1,
          example_ids: [1],
          message: 'Successfully approved 1 examples. Supabase sync in progress.'
        }
      })
    }).as('approveSpecific')

    // Load conversation
    cy.contains('Test Conversation').click()
    cy.wait('@getExamples')

    // Deselect low confidence example
    cy.get('[data-testid="example-checkbox-2"]').click()

    // Approve selected only
    cy.get('[data-testid="approve-selected-button"]').click()

    // Confirm dialog
    cy.get('[data-testid="approval-dialog"]').within(() => {
      cy.get('input[name="approved_by"]').type('test@example.com')
      cy.get('button[type="submit"]').click()
    })

    cy.wait('@approveSpecific')

    // Verify only 1 example approved
    cy.get('[data-testid="toast"]')
      .should('contain', 'Successfully approved 1 examples')
  })
})