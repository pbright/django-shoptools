# from datetime import datetime
import uuid

from django.db import models
from django.template.defaultfilters import floatformat
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from model_utils.managers import InheritanceManager

from cart.models import ICart
from checkout.models import Order


def get_vouchers(codes):
    return BaseVoucher.objects.select_subclasses().filter(code__in=codes)


def calculate_discounts(obj, vouchers):
    """Calculate the total discount for an ICart instance, for the given
       vouchers. Return a list of Discount instances (unsaved)
       - Multiple percentage vouchers, just take the biggest
       - Multiple fixed vouchers are combined
       - Percentage discounts are applied first, then fixed.
    """

    assert isinstance(obj, ICart)

    discounts = []
    total = obj.subtotal + obj.shipping_cost

    # if obj is an order, and the voucher has already been used on that order,
    # those instances are ignored when checking limits etc, since they will be
    # overridden when it's saved. The order is also attached to each Discount
    # instance
    if isinstance(obj, Order):
        defaults = {'order': obj}
    else:
        defaults = {}

    # filter out any that have already been used
    vouchers = filter(lambda v: v.available(exclude=defaults), vouchers)

    # find and apply best percentage voucher
    percentage = filter(lambda v: isinstance(v, PercentageVoucher), vouchers)
    p_voucher = None
    for voucher in percentage:
        if isinstance(voucher, PercentageVoucher) and \
                (not p_voucher or p_voucher.amount < voucher.amount):
            p_voucher = voucher
    if p_voucher:
        amount = min(total, total * p_voucher.amount / 100)
        total -= amount
        discounts.append(
            Discount(voucher=p_voucher, amount=amount, **defaults))

    # apply fixed vouchers, smallest remaining amount first
    fixed = filter(lambda v: isinstance(v, FixedVoucher), vouchers)
    fixed.sort(key=lambda v: v.amount_remaining)
    for voucher in fixed:
        amount = min(total, voucher.amount, voucher.amount_remaining)
        if amount == 0:
            continue
        total -= amount
        discounts.append(Discount(voucher=voucher, amount=amount, **defaults))

    return discounts


def save_discounts(obj, vouchers):
    assert isinstance(obj, Order)

    for discount in calculate_discounts(obj, vouchers):
        discount.save()


def make_code():
    u = uuid.uuid4()
    return str(u).replace('-', '')[:8]


class BaseVoucher(models.Model):
    code = models.CharField(max_length=32, blank=True, unique=True,
                            help_text=u"Leave blank to auto-generate")
    created = models.DateTimeField(auto_now_add=True)
    limit = models.PositiveSmallIntegerField(null=True, blank=True)

    objects = InheritanceManager()

    @property
    def voucher(self):
        qs = BaseVoucher.objects.select_subclasses()
        return qs.get(pk=self.pk)

    @property
    def base_voucher(self):
        return BaseVoucher.objects.get(pk=self.pk)

    def uses(self, exclude={}):
        return Discount.objects.exclude(**exclude) \
                               .filter(base_voucher=self.base_voucher)

    def available(self, exclude={}):
        if self.limit is None:
            return True
        return bool(self.limit - self.uses(exclude).count())

    def amount_used(self, exclude={}):
        uses = self.uses(exclude)
        return uses.aggregate(models.Sum('amount'))['amount__sum']

    def amount_remaining(self, exclude={}):
        """Return dollar amount remaining on a voucher, where it makes sense.
           If not, return None to indicate an unlimited amount remaining.
        """

        if not isinstance(self.voucher, FixedVoucher) or self.limit is None:
            return None

        return self.amount * self.limit - self.amount_used(exclude)

    def clean(self):
        if not self.code:
            self.code = make_code()

    def __unicode__(self):
        return self.voucher.discount_text


class FixedVoucher(BaseVoucher):
    amount = models.DecimalField(max_digits=6, decimal_places=2)

    @property
    def discount_text(self):
        return '$%s voucher' % floatformat(self.amount, -2)


class PercentageVoucher(BaseVoucher):
    amount = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(100)])

    @property
    def discount_text(self):
        return '%s%% discount' % floatformat(self.amount, -2)


class Discount(models.Model):
    order = models.ForeignKey(Order)
    base_voucher = models.ForeignKey(BaseVoucher)
    amount = models.DecimalField(max_digits=6, decimal_places=2)

    def __init__(self, *args, **kwargs):
        voucher = kwargs.pop('voucher', None)
        if voucher:
            kwargs['base_voucher'] = voucher.base_voucher
        super(Discount, self).__init__(*args, **kwargs)

    @property
    def voucher(self):
        return self.base_voucher.voucher

    @voucher.setter
    def voucher(self, voucher_obj):
        self.base_voucher = voucher_obj.base_voucher

    def clean(self):
        """Verify that the voucher doesn't violate
           - the usage limit (if there is one)
           - the fixed amount (for fixed vouchers)
           - the total remaining amount (for limited-use, fixed vouchers)
        """

        voucher = self.voucher
        uses = voucher.uses(exclude={'pk': self.pk})

        if voucher.limit is not None and uses.count() > voucher.limit:
            raise ValidationError(u"Voucher has already been used")

        if isinstance(voucher, FixedVoucher):
            if self.amount > voucher.amount:
                raise ValidationError(u"Discount exceeds voucher amount")

        remaining = voucher.amount_remaining(exclude={'pk': self.pk})
        if remaining is not None and self.amount > remaining:
            msg = u"Discount exceeds voucher's remaining balance"
            raise ValidationError(msg)

    def __unicode__(self):
        if self.pk:
            return u"%s: %s" % (self.order, self.voucher)
        else:
            return unicode(self.voucher)