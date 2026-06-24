<script setup>
const clientWorkspaceUrl = '/users/clients/'
</script>

<template>
  <section class="workspace">
    <div class="section-heading compact">
      <div>
        <h2>Client Management</h2>
        <p class="muted">Open client locator, journey tracking, referrals, follow-up tasks, appointment history, and consent controls.</p>
      </div>
      <a class="primary-action" :href="clientWorkspaceUrl">
        <span class="material-symbols-outlined" aria-hidden="true">open_in_new</span>
        Open Workspace
      </a>
    </div>

    <div class="panel-grid">
      <article class="panel">
        <span class="material-symbols-outlined">badge</span>
        <h3>Client profile / alias</h3>
        <p class="muted">Use non-identifying reference details and contact preferences.</p>
      </article>
      <article class="panel">
        <span class="material-symbols-outlined">route</span>
        <h3>Journey tracking</h3>
        <p class="muted">Track contact, risk assessment, referral, HIVST, initiation, follow-up, and continuation.</p>
      </article>
      <article class="panel">
        <span class="material-symbols-outlined">assignment_returned</span>
        <h3>Referral history</h3>
        <p class="muted">Record receiving hub, confirmation status, and initiation outcome.</p>
      </article>
      <article class="panel">
        <span class="material-symbols-outlined">task_alt</span>
        <h3>Follow-up tasks</h3>
        <p class="muted">Create tracing, missed appointment, referral confirmation, and re-engagement tasks.</p>
      </article>
    </div>
  </section>
</template>
