from datetime import datetime
import uuid

from django.db import models
from django.contrib.contenttypes.fields import GenericRelation
from django.core.urlresolvers import reverse
from django.conf import settings

from cart.models import OrderLine
from dps.models import FullTransactionProtocol, Transaction
# from paypal.models import FullTransactionProtocol, Transaction

from .emails import send_email_receipt
from .shipping import calculate_shipping


DEFAULT_CURRENCY = getattr(settings, 'DEFAULT_CURRENCY', 'NZD')


def make_uuid():
    """the hyphens in uuids are unnecessary, and brevity will be an
    advantage in our urls."""
    u = uuid.uuid4()
    return str(u).replace('-', '')


class Order(models.Model, FullTransactionProtocol):
    STATUS_NEW = "new"
    STATUS_PAID = "paid"
    STATUS_PAYMENT_FAILED = "payment_failed"
    STATUS_SHIPPED = "shipped"

    STATUS_CHOICES = [
        (STATUS_NEW, "New"),
        (STATUS_PAID, "Paid"),
        (STATUS_PAYMENT_FAILED, "Payment Failed"),
        (STATUS_SHIPPED, "Shipped"),
    ]
    
    secret = models.CharField(max_length=32, editable=False, default=make_uuid,
                              unique=True, db_index=True)
    name = models.CharField(u"Name", max_length=1023, default="")
    street = models.CharField(u"Address", max_length=1023)
    suburb = models.CharField(max_length=255, blank=True)
    postcode = models.CharField(max_length=100)
    city = models.CharField(u"Town / City", max_length=255)
    country = models.CharField(max_length=255, default=u'New Zealand')
    email = models.EmailField()
    currency = models.CharField(max_length=3, editable=False, 
                                default=DEFAULT_CURRENCY)
    created = models.DateTimeField(default=datetime.now)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES,
                              default=STATUS_NEW)
    amount_paid = models.DecimalField(max_digits=8, decimal_places=2, default=0)

    lines = GenericRelation(OrderLine,
                                    content_type_field='parent_content_type',
                                    object_id_field='parent_object_id')
    
    payments = GenericRelation(Transaction)
    
    @models.permalink
    def get_success_url(self):
        return ('checkout_success', (self.secret,))
    
    @models.permalink
    def get_absolute_url(self):
        return ('checkout_checkout', (self.secret,))
    
    @property
    def invoice_number(self):
        return str(self.pk).zfill(5)
    
    def __unicode__(self):
        return u"%s on %s" % (self.name, self.created)
    
    def shipping_cost(self):
        return calculate_shipping(self.lines.all(), order=self)
    
    def total(self):
        val = 0
        for line in self.lines.all():
            val += line.total

        return val + self.shipping_cost()
    
    get_amount = total
    
    def is_recurring(self):
        return False

    def transaction_succeeded(self, transaction, interactive, status_updated):
        if status_updated:
            self.amount_paid = transaction.amount
            self.status = self.STATUS_PAID
            self.save()
            send_email_receipt(self)
        return self.get_success_url()
    
    def transaction_failed(self, transaction, interactive, status_updated):
        if status_updated:
            self.status = self.STATUS_PAYMENT_FAILED
            self.save()
        
        return self.get_absolute_url()
    
    def get_lines(self):
        for line in self.lines.all():
            yield (line.description, line.quantity, line.total)
