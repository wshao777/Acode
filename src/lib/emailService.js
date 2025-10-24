import settings from './settings';

/**
 * Sends a bank transaction notification.
 * In a real-world scenario, this would use an SMTP client or an email API.
 * For this implementation, it will log the notification to the console.
 *
 * @param {string} subject - The subject of the notification.
 * @param {string} body - The body of the notification.
 */
function sendBankNotification(subject, body) {
  const recipient = settings.value.bank_notification_email;

  if (!recipient) {
    console.error("Bank notification email recipient is not configured.");
    return;
  }

  console.log("--- SIMULATING BANK NOTIFICATION EMAIL ---");
  console.log(`To: ${recipient}`);
  console.log(`Subject: ${subject}`);
  console.log(`Body: ${body}`);
  console.log("-----------------------------------------");
}

export {
  sendBankNotification,
};
