const type = document.getElementById('task_type');
const orderFields = document.getElementById('order-fields');
const placed = document.getElementById('order_placed');
const delivered = document.getElementById('order_delivered');

function updateFields() {
  const isOrder = type.value === 'order';
  for (const role of ['customer', 'supplier', 'other']) {
    const fields = document.getElementById(`${role}-fields`);
    const visible = role !== 'other' || !isOrder;
    fields.hidden = !visible;
    fields.disabled = !visible;
    document.getElementById(role).required = isOrder && role !== 'other';
  }
  orderFields.hidden = !isOrder;
  orderFields.disabled = !isOrder;
  updateValidity();
}

function updateValidity() {
  const isOrder = type.value === 'order';
  const hasContact = ['customer', 'supplier', 'other'].some(
    role => document.getElementById(role).value.trim().length > 0
  );
  document.getElementById('customer').setCustomValidity(
    !isOrder && !hasContact ? 'Enter at least one contact: customer, supplier or other.' : ''
  );
  delivered.setCustomValidity(
    isOrder && delivered.checked && !placed.checked
      ? 'Mark the order as placed before marking it as delivered.' : ''
  );
}

type.addEventListener('change', updateFields);
for (const role of ['customer', 'supplier', 'other']) {
  document.getElementById(role).addEventListener('input', updateValidity);
}
placed.addEventListener('change', updateValidity);
delivered.addEventListener('change', updateValidity);
updateFields();
