# Selenium Java Reference Guide

This document details how the `regression-test-selector` parses, indexes, and targets Selenium Java automation repositories (using TestNG or JUnit).

---

## 1. Project Detection
A repository is recognized as a Selenium Java project when:
- `pom.xml` or `build.gradle` is present, AND
- Test files matching `*Test.java`, `*Tests.java`, or `*IT.java` exist.

---

## 2. Test Annotations and Metadata Extraction

### TestNG and JUnit Annotations
The indexer recognizes standard test annotations:
```java
@Test(groups = {"regression", "payment"}, description = "[PAY-101] Process Credit Card Payment with 3DS")
public void testPaymentOrderSubmission() {
    CheckoutPage checkout = new CheckoutPage(driver);
    checkout.navigate();
    checkout.submitOrder();
}
```

The parser extracts:
- **Test ID**: `src/test/java/com/psp/tests/PaymentProcessingTest.java:13:PaymentProcessingTest.testPaymentOrderSubmission`
- **Groups / Tags**: Converted to standardized tags (e.g. `@regression`, `@payment`).
- **Jira Keys**: Extracted from `@description`, JavaDoc comments (`* Jira: PAY-101`), or git log history of the file.

---

## 3. Selenium Page Object / PageFactory Indirection

Selenium projects commonly encapsulate driver calls in Page Objects:
```java
public class CheckoutPage {
    public static final String CHECKOUT_URL = "/checkout/payment";
    
    @FindBy(id = "card-number-input")
    private WebElement cardNumber;
    
    @FindBy(id = "btn-submit-order")
    private WebElement payButton;
}
```

The indexer resolves:
1. Constant URLs and route strings (e.g. `driver.get(...)`, `/checkout/payment`).
2. `@FindBy` selectors (`id`, `name`, `xpath`, `css`).
3. Inherits these attributes into tests instantiating `CheckoutPage`.

---

## 4. Execution Command Generation

### Maven Surefire Plugin
To execute individual selected methods in Maven:
```bash
mvn test -Dtest=PaymentProcessingTest#testPaymentOrderSubmission,PaymentProcessingTest#testCardDecline
```

### Group Execution Fallback
For group-based execution:
```bash
mvn test -Dgroups=regression,smoke
```
